"""PostgreSQL outbox repository implementation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from persistence.errors import PersistenceNotFoundError
from persistence.repos._base import PostgresRepoBase
from persistence.repos._mappers import OutboxRow
from persistence.repos._sql import OUTBOX
from persistence.types import OutboxEntry, OutboxInsertSpec, OutboxStatus


class PostgresOutboxRepo(PostgresRepoBase):
    """Transactional outbox for at-least-once task dispatch."""

    def insert(self, spec: OutboxInsertSpec) -> OutboxEntry:
        operation = "insert"
        self._require_active_transaction(operation)
        outbox_id = str(uuid4())
        now = datetime.now(UTC)
        try:
            conn = self._connection()
            conn.execute(
                OUTBOX,
                (
                    outbox_id,
                    spec.workflow_id,
                    spec.task_id,
                    self._mapper.task_type_to_db(spec.task_type),
                    spec.payload_reference.ref_id,
                    spec.payload_reference.ref_kind,
                    spec.idempotency_key,
                    self._mapper.outbox_status_to_db(OutboxStatus.PENDING),
                    now,
                    None,
                ),
                prepare=False,
            )
            entry = OutboxEntry(
                outbox_id=outbox_id,
                workflow_id=spec.workflow_id,
                task_id=spec.task_id,
                task_type=spec.task_type,
                payload_reference=spec.payload_reference,
                idempotency_key=spec.idempotency_key,
                status=OutboxStatus.PENDING,
                created_at=now,
                published_at=None,
            )
            self._record_success(operation)
            return entry
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=outbox_id)

    def fetch_unpublished(self, limit: int) -> Sequence[OutboxEntry]:
        operation = "fetch_unpublished"
        try:
            with self._borrow_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT outbox_id, workflow_id, task_id, task_type,
                           payload_ref_id, payload_ref_kind, idempotency_key,
                           status, created_at, published_at
                    FROM outbox
                    WHERE status = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (self._mapper.outbox_status_to_db(OutboxStatus.PENDING), limit),
                    prepare=False,
                ).fetchall()
            entries = [
                self._mapper.to_outbox_entry(self._outbox_row_from_dict(row))
                for row in rows
            ]
            self._record_success(operation)
            return entries
        except Exception as exc:
            self._raise_mapped(exc, operation=operation)

    def mark_published(
        self, outbox_id: str, *, published_at: datetime
    ) -> OutboxEntry:
        operation = "mark_published"
        try:
            existing = self._fetch_entry(outbox_id)
            if existing is None:
                not_found = PersistenceNotFoundError(
                    f"Outbox entry {outbox_id} not found"
                )
                self._log_error(operation, not_found, outbox_id)
                raise not_found
            if existing.status == OutboxStatus.PUBLISHED:
                self._record_success(operation)
                return existing
            updated = self._update_published(outbox_id, published_at=published_at)
            if updated is None:
                refreshed = self._fetch_entry(outbox_id)
                if refreshed is not None and refreshed.status == OutboxStatus.PUBLISHED:
                    self._record_success(operation)
                    return refreshed
                not_found = PersistenceNotFoundError(
                    f"Outbox entry {outbox_id} not found"
                )
                self._log_error(operation, not_found, outbox_id)
                raise not_found
            self._record_success(operation)
            return updated
        except PersistenceNotFoundError:
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=outbox_id)

    def _fetch_entry(self, outbox_id: str) -> OutboxEntry | None:
        with self._borrow_connection() as conn:
            row = conn.execute(
                """
                SELECT outbox_id, workflow_id, task_id, task_type,
                       payload_ref_id, payload_ref_kind, idempotency_key,
                       status, created_at, published_at
                FROM outbox
                WHERE outbox_id = %s
                """,
                (outbox_id,),
                prepare=False,
            ).fetchone()
        if row is None:
            return None
        return self._mapper.to_outbox_entry(self._outbox_row_from_dict(row))

    def _update_published(
        self, outbox_id: str, *, published_at: datetime
    ) -> OutboxEntry | None:
        with self._borrow_connection() as conn:
            row = conn.execute(
                """
                UPDATE outbox
                SET status = %s, published_at = %s
                WHERE outbox_id = %s AND status = %s
                RETURNING outbox_id, workflow_id, task_id, task_type,
                          payload_ref_id, payload_ref_kind, idempotency_key,
                          status, created_at, published_at
                """,
                (
                    self._mapper.outbox_status_to_db(OutboxStatus.PUBLISHED),
                    published_at,
                    outbox_id,
                    self._mapper.outbox_status_to_db(OutboxStatus.PENDING),
                ),
                prepare=False,
            ).fetchone()
        if row is None:
            return None
        return self._mapper.to_outbox_entry(self._outbox_row_from_dict(row))

    @staticmethod
    def _outbox_row_from_dict(row: dict[str, Any]) -> OutboxRow:
        return OutboxRow(
            outbox_id=str(row["outbox_id"]),
            workflow_id=str(row["workflow_id"]),
            task_id=str(row["task_id"]),
            task_type=str(row["task_type"]),
            payload_ref_id=str(row["payload_ref_id"]),
            payload_ref_kind=str(row["payload_ref_kind"]),
            idempotency_key=str(row["idempotency_key"]),
            status=str(row["status"]),
            created_at=row["created_at"],  # type: ignore[arg-type]
            published_at=row.get("published_at"),  # type: ignore[arg-type]
        )
