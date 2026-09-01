"""Pre-code test mold for PERS-010 — PostgresTaskLeaseRepo (LLD §3.9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from psycopg.errors import UniqueViolation

from persistence import PersistenceConnectionError


def test_second_acquire_returns_none() -> None:
    """Second try_acquire while lease active → None (PERS-TC-041)."""
    from persistence.repos.task_lease import PostgresTaskLeaseRepo

    fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    repo = PostgresTaskLeaseRepo(clock=lambda: fixed_now)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_delete_expired", MagicMock())
        mp.setattr(
            repo,
            "_insert_lease",
            MagicMock(side_effect=[MagicMock(), UniqueViolation("unique")]),
        )

        first = repo.try_acquire("task-1", worker_id="worker-a", ttl_seconds=60.0)
        second = repo.try_acquire("task-1", worker_id="worker-b", ttl_seconds=60.0)

    assert first is not None
    assert second is None


def test_acquire_connection_error_is_not_swallowed() -> None:
    """Non-conflict failures during try_acquire propagate as PersistenceConnectionError."""
    from persistence.repos.task_lease import PostgresTaskLeaseRepo

    repo = PostgresTaskLeaseRepo()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_delete_expired", MagicMock())
        mp.setattr(
            repo,
            "_insert_lease",
            MagicMock(side_effect=RuntimeError("connection lost")),
        )

        with pytest.raises(PersistenceConnectionError):
            repo.try_acquire("task-1", worker_id="worker-a", ttl_seconds=60.0)


def test_clock_injected_expiry_allows_reacquire() -> None:
    """Expired lease (injected clock) allows new acquire (PERS-TC-042)."""
    from persistence.repos.task_lease import PostgresTaskLeaseRepo

    clock_values = [
        datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC),
    ]
    repo = PostgresTaskLeaseRepo(clock=lambda: clock_values.pop(0))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_delete_expired", MagicMock())
        mp.setattr(
            repo,
            "_insert_lease",
            MagicMock(
                side_effect=[
                    MagicMock(expires_at=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC)),
                    MagicMock(expires_at=datetime(2026, 1, 1, 12, 6, 0, tzinfo=UTC)),
                ]
            ),
        )

        first = repo.try_acquire("task-1", worker_id="worker-a", ttl_seconds=60.0)
        second = repo.try_acquire("task-1", worker_id="worker-b", ttl_seconds=60.0)

    assert first is not None
    assert second is not None
