"""PostgreSQL task lease repository implementation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.errors import UniqueViolation

from persistence.errors import PersistenceNotFoundError
from persistence.repos._base import PostgresRepoBase
from persistence.repos._mappers import TaskLeaseRow
from persistence.repos._sql import TASK_LEASES
from persistence.types import TaskLease


class PostgresTaskLeaseRepo(PostgresRepoBase):
    """Short-lived in-flight task leases."""

    def __init__(
        self,
        pool_manager: object | None = None,
        *,
        mapper: object | None = None,
        error_translator: object | None = None,
        operation_logger: object | None = None,
        metrics_recorder: object | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            pool_manager,  # type: ignore[arg-type]
            mapper=mapper,  # type: ignore[arg-type]
            error_translator=error_translator,  # type: ignore[arg-type]
            operation_logger=operation_logger,  # type: ignore[arg-type]
            metrics_recorder=metrics_recorder,  # type: ignore[arg-type]
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        return self._clock()

    def try_acquire(
        self, task_id: str, *, worker_id: str, ttl_seconds: float
    ) -> TaskLease | None:
        operation = "try_acquire"
        self._delete_expired(task_id)
        try:
            lease = self._insert_lease(
                task_id,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
            )
            self._record_success(operation)
            return lease
        except UniqueViolation:
            return None
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=task_id)

    def renew(self, lease_id: str, *, ttl_seconds: float) -> TaskLease:
        operation = "renew"
        expires_at = self._now() + timedelta(seconds=ttl_seconds)
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    UPDATE task_leases
                    SET expires_at = %s
                    WHERE lease_id = %s AND expires_at > %s
                    RETURNING lease_id, task_id, worker_id, acquired_at, expires_at
                    """,
                    (expires_at, lease_id, self._now()),
                    prepare=False,
                ).fetchone()
            if row is None:
                not_found = PersistenceNotFoundError(f"Lease {lease_id} not found")
                self._log_error(operation, not_found, lease_id)
                raise not_found
            record = self._mapper.to_task_lease(
                TaskLeaseRow(
                    lease_id=str(row["lease_id"]),
                    task_id=str(row["task_id"]),
                    worker_id=str(row["worker_id"]),
                    acquired_at=row["acquired_at"],  # type: ignore[arg-type]
                    expires_at=row["expires_at"],  # type: ignore[arg-type]
                )
            )
            self._record_success(operation)
            return record
        except PersistenceNotFoundError:
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=lease_id)

    def release(self, lease_id: str) -> None:
        operation = "release"
        try:
            with self._borrow_connection() as conn:
                conn.execute(
                    "DELETE FROM task_leases WHERE lease_id = %s",
                    (lease_id,),
                    prepare=False,
                )
            self._record_success(operation)
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=lease_id)

    def get_active_lease(self, task_id: str) -> TaskLease | None:
        operation = "get_active_lease"
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    SELECT lease_id, task_id, worker_id, acquired_at, expires_at
                    FROM task_leases
                    WHERE task_id = %s AND expires_at > %s
                    """,
                    (task_id, self._now()),
                    prepare=False,
                ).fetchone()
            if row is None:
                return None
            record = self._mapper.to_task_lease(
                TaskLeaseRow(
                    lease_id=str(row["lease_id"]),
                    task_id=str(row["task_id"]),
                    worker_id=str(row["worker_id"]),
                    acquired_at=row["acquired_at"],  # type: ignore[arg-type]
                    expires_at=row["expires_at"],  # type: ignore[arg-type]
                )
            )
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=task_id)

    def _delete_expired(self, task_id: str) -> None:
        with self._borrow_connection() as conn:
            conn.execute(
                """
                DELETE FROM task_leases
                WHERE task_id = %s AND expires_at < %s
                """,
                (task_id, self._now()),
                prepare=False,
            )

    def _insert_lease(
        self,
        task_id: str,
        *,
        worker_id: str,
        ttl_seconds: float,
    ) -> TaskLease:
        lease_id = str(uuid4())
        acquired_at = self._now()
        expires_at = acquired_at + timedelta(seconds=ttl_seconds)
        with self._borrow_connection() as conn:
            conn.execute(
                TASK_LEASES,
                (lease_id, task_id, worker_id, acquired_at, expires_at),
                prepare=False,
            )
        return TaskLease(
            lease_id=lease_id,
            task_id=task_id,
            worker_id=worker_id,
            acquired_at=acquired_at,
            expires_at=expires_at,
        )
