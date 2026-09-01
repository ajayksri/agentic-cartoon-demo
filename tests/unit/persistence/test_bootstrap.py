"""Pre-code test mold for PERS-011 — create_persistence_stack (LLD §7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from persistence import PersistenceConnectionError


def _connection_settings():
    from persistence.bootstrap import ConnectionSettings

    return ConnectionSettings(
        host="localhost",
        port=5432,
        database="test",
        user="tester",
        password="secret",
        min_pool_size=1,
        max_pool_size=2,
        connection_timeout_seconds=5.0,
    )


def test_health_check_failure_on_bootstrap_raises_connection_error() -> None:
    """health_check_on_bootstrap failure → PersistenceConnectionError at startup."""
    from persistence.bootstrap import PersistenceStackOptions, create_persistence_stack

    settings = _connection_settings()
    options = PersistenceStackOptions(health_check_on_bootstrap=True)

    with patch("persistence.pool.ConnectionPoolManager") as pool_cls:
        pool_cls.return_value.health_check.side_effect = PersistenceConnectionError()
        with pytest.raises(PersistenceConnectionError):
            create_persistence_stack(settings, options=options)


def test_create_persistence_stack_returns_wired_bundle() -> None:
    """create_persistence_stack returns PersistenceBundle with all repo fields."""
    from persistence.bootstrap import create_persistence_stack

    settings = _connection_settings()

    with patch("persistence.pool.ConnectionPoolManager") as pool_cls:
        pool_cls.return_value.health_check.return_value = None
        bundle = create_persistence_stack(settings)

    for field in (
        "pool_manager",
        "transaction_manager",
        "workflow_repo",
        "artifact_repo",
        "idempotency_repo",
        "outbox_repo",
        "task_lease_repo",
    ):
        assert getattr(bundle, field) is not None, f"missing bundle.{field}"
