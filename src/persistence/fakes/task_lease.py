"""In-memory task lease repository fake."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from persistence.errors import PersistenceNotFoundError
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import TaskLease


class InMemoryTaskLeaseRepo:
    """Dict-backed task lease repository for tests."""

    def __init__(
        self,
        *,
        transaction_manager: InMemoryTransactionManager | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._leases: dict[str, TaskLease] = {}
        self._clock = clock or (lambda: datetime.now(UTC))
        if transaction_manager is not None:
            transaction_manager.register_store(self._snapshot, self._restore)

    def _snapshot(self) -> dict[str, TaskLease]:
        return copy.deepcopy(self._leases)

    def _restore(self, snapshot: dict[str, TaskLease]) -> None:
        self._leases = snapshot

    def _now(self) -> datetime:
        return self._clock()

    def try_acquire(
        self, task_id: str, *, worker_id: str, ttl_seconds: float
    ) -> TaskLease | None:
        self._delete_expired(task_id)
        if task_id in self._leases:
            return None
        lease_id = str(uuid4())
        acquired_at = self._now()
        lease = TaskLease(
            lease_id=lease_id,
            task_id=task_id,
            worker_id=worker_id,
            acquired_at=acquired_at,
            expires_at=acquired_at + timedelta(seconds=ttl_seconds),
        )
        self._leases[task_id] = lease
        return lease

    def renew(self, lease_id: str, *, ttl_seconds: float) -> TaskLease:
        for task_id, lease in list(self._leases.items()):
            if lease.lease_id != lease_id:
                continue
            if lease.expires_at <= self._now():
                raise PersistenceNotFoundError(f"Lease {lease_id} not found")
            renewed = TaskLease(
                lease_id=lease.lease_id,
                task_id=lease.task_id,
                worker_id=lease.worker_id,
                acquired_at=lease.acquired_at,
                expires_at=self._now() + timedelta(seconds=ttl_seconds),
            )
            self._leases[task_id] = renewed
            return renewed
        raise PersistenceNotFoundError(f"Lease {lease_id} not found")

    def release(self, lease_id: str) -> None:
        for task_id, lease in list(self._leases.items()):
            if lease.lease_id == lease_id:
                del self._leases[task_id]
                return

    def get_active_lease(self, task_id: str) -> TaskLease | None:
        lease = self._leases.get(task_id)
        if lease is None or lease.expires_at <= self._now():
            return None
        return lease

    def _delete_expired(self, task_id: str) -> None:
        lease = self._leases.get(task_id)
        if lease is not None and lease.expires_at < self._now():
            del self._leases[task_id]
