"""Lease lifecycle orchestration (LLD §4.4)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Task leases — short-lived locks prevent concurrent
# workers from executing the same in-flight task while allowing redelivery after expiry.
# GUARDRAIL: Execution — only one worker may execute a given task attempt at a time.

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from persistence.errors import PersistenceNotFoundError
from persistence.protocols import TaskLeaseRepo
from persistence.types import TaskLease

from .constants import (
    DEFAULT_LEASE_RENEW_INTERVAL_SECONDS,
    DEFAULT_LEASE_TTL_SECONDS,
)
from .errors import LeaseConflictError
from .messages import lease_conflict_message


class LeaseCoordinator:
    """Acquire, renew, and release task leases."""

    def __init__(
        self,
        *,
        task_lease_repo: TaskLeaseRepo,
        ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
        renew_interval_seconds: int = DEFAULT_LEASE_RENEW_INTERVAL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._task_lease_repo = task_lease_repo
        self._ttl_seconds = ttl_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._renew_failed = False
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    @property
    def renew_failed(self) -> bool:
        return self._renew_failed

    def acquire(self, *, task_id: str, worker_id: str) -> TaskLease:
        lease = self._task_lease_repo.try_acquire(
            task_id,
            worker_id=worker_id,
            ttl_seconds=float(self._ttl_seconds),
        )
        if lease is None:
            raise LeaseConflictError(
                lease_conflict_message(task_id=task_id, worker_id=worker_id),
                task_id=task_id,
                worker_id=worker_id,
            )
        return lease

    def start_renewal(self, *, lease_id: str) -> None:
        self._renew_failed = False
        self._schedule_renewal(lease_id)

    def _schedule_renewal(self, lease_id: str) -> None:
        timer = threading.Timer(
            self._renew_interval_seconds,
            self._renew_lease,
            args=(lease_id,),
        )
        timer.daemon = True
        with self._lock:
            self._timers[lease_id] = timer
        timer.start()

    def _renew_lease(self, lease_id: str) -> None:
        if self._renew_failed:
            return
        try:
            self._task_lease_repo.renew(
                lease_id,
                ttl_seconds=float(self._ttl_seconds),
            )
        except PersistenceNotFoundError:
            self._renew_failed = True
            return
        self._schedule_renewal(lease_id)

    def stop_renewal(self, *, lease_id: str) -> None:
        with self._lock:
            timer = self._timers.pop(lease_id, None)
        if timer is not None:
            timer.cancel()

    def release(self, *, lease_id: str) -> None:
        self.stop_renewal(lease_id=lease_id)
        self._task_lease_repo.release(lease_id)
