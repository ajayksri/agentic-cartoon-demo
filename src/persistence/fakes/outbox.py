"""In-memory outbox repository fake."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from persistence.errors import PersistenceNotFoundError, PersistenceTransactionError
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import OutboxEntry, OutboxInsertSpec, OutboxStatus


class InMemoryOutboxRepo:
    """List-backed outbox repository for tests."""

    def __init__(
        self,
        *,
        transaction_manager: InMemoryTransactionManager | None = None,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._entries: dict[str, OutboxEntry] = {}
        if transaction_manager is not None:
            transaction_manager.register_store(self._snapshot, self._restore)

    def _snapshot(self) -> dict[str, OutboxEntry]:
        return copy.deepcopy(self._entries)

    def _restore(self, snapshot: dict[str, OutboxEntry]) -> None:
        self._entries = snapshot

    def _require_active_transaction(self, operation: str) -> None:
        if (
            self._transaction_manager is None
            or not self._transaction_manager.is_in_transaction()
        ):
            raise PersistenceTransactionError(
                f"Operation {operation} requires an active transaction"
            )

    def insert(self, spec: OutboxInsertSpec) -> OutboxEntry:
        operation = "insert"
        self._require_active_transaction(operation)
        outbox_id = str(uuid4())
        now = datetime.now(UTC)
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
        self._entries[outbox_id] = entry
        return entry

    def fetch_unpublished(self, limit: int) -> Sequence[OutboxEntry]:
        pending = [
            entry
            for entry in self._entries.values()
            if entry.status == OutboxStatus.PENDING
        ]
        pending.sort(key=lambda e: e.created_at)
        return pending[:limit]

    def mark_published(
        self, outbox_id: str, *, published_at: datetime
    ) -> OutboxEntry:
        existing = self._entries.get(outbox_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Outbox entry {outbox_id} not found")
        if existing.status == OutboxStatus.PUBLISHED:
            return existing
        updated = OutboxEntry(
            outbox_id=existing.outbox_id,
            workflow_id=existing.workflow_id,
            task_id=existing.task_id,
            task_type=existing.task_type,
            payload_reference=existing.payload_reference,
            idempotency_key=existing.idempotency_key,
            status=OutboxStatus.PUBLISHED,
            created_at=existing.created_at,
            published_at=published_at,
        )
        self._entries[outbox_id] = updated
        return updated
