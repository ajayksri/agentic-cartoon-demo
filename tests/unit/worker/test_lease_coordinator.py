"""Unit tests for WKR-003 LeaseCoordinator (LLD §4.4)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from persistence.fakes.task_lease import InMemoryTaskLeaseRepo
from worker.errors import LeaseConflictError
from worker.lease import LeaseCoordinator


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


def test_acquire_success() -> None:
    repo = InMemoryTaskLeaseRepo()
    coordinator = LeaseCoordinator(task_lease_repo=repo, renew_interval_seconds=3600)
    lease = coordinator.acquire(task_id="task-1", worker_id="worker-1")
    assert lease.task_id == "task-1"
    assert lease.worker_id == "worker-1"


def test_acquire_conflict_raises() -> None:
    repo = InMemoryTaskLeaseRepo()
    coordinator = LeaseCoordinator(task_lease_repo=repo)
    coordinator.acquire(task_id="task-1", worker_id="worker-1")
    with pytest.raises(LeaseConflictError) as exc_info:
        coordinator.acquire(task_id="task-1", worker_id="worker-2")
    assert exc_info.value.task_id == "task-1"
    assert exc_info.value.worker_id == "worker-2"


def test_stop_renewal_is_idempotent() -> None:
    repo = InMemoryTaskLeaseRepo()
    coordinator = LeaseCoordinator(task_lease_repo=repo, renew_interval_seconds=3600)
    lease = coordinator.acquire(task_id="task-1", worker_id="worker-1")
    coordinator.start_renewal(lease_id=lease.lease_id)
    coordinator.stop_renewal(lease_id=lease.lease_id)
    coordinator.stop_renewal(lease_id=lease.lease_id)


def test_renew_failure_sets_flag() -> None:
    clock = _MutableClock(datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC))
    repo = InMemoryTaskLeaseRepo(clock=clock)
    coordinator = LeaseCoordinator(
        task_lease_repo=repo,
        ttl_seconds=1,
        renew_interval_seconds=0.05,
        clock=clock,
    )
    lease = coordinator.acquire(task_id="task-1", worker_id="worker-1")
    coordinator.start_renewal(lease_id=lease.lease_id)
    clock.advance(2.0)
    time.sleep(0.15)
    assert coordinator.renew_failed
