"""Pre-code test mold for PERS-003 — ConnectionPoolManager (LLD §3.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from persistence import PersistenceConnectionError


def test_health_check_failure_raises_connection_error() -> None:
    """Health check SELECT 1 failure → PersistenceConnectionError."""
    from persistence.bootstrap import ConnectionSettings
    from persistence.pool import ConnectionPoolManager

    settings = ConnectionSettings(
        host="localhost",
        port=5432,
        database="test",
        user="tester",
        password="secret",
        min_pool_size=1,
        max_pool_size=2,
        connection_timeout_seconds=5.0,
    )
    manager = ConnectionPoolManager(settings)

    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = Exception("connection refused")
    mock_pool.connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(manager, "_pool", mock_pool):
        with pytest.raises(PersistenceConnectionError) as exc_info:
            manager.health_check()

    assert exc_info.value.code == "PERS_CONNECTION"


def test_pool_is_open_after_construction() -> None:
    """ConnectionPoolManager opens pool on construction for acquire/health_check."""
    from persistence.bootstrap import ConnectionSettings
    from persistence.pool import ConnectionPoolManager

    settings = ConnectionSettings(
        host="localhost",
        port=5432,
        database="test",
        user="tester",
        password="secret",
        min_pool_size=1,
        max_pool_size=2,
        connection_timeout_seconds=5.0,
    )
    manager = ConnectionPoolManager(settings)

    try:
        assert manager._pool.closed is False
    finally:
        manager.close()


def test_pool_exhaustion_raises_connection_error() -> None:
    """Pool exhaustion on acquire → PersistenceConnectionError."""
    from persistence.bootstrap import ConnectionSettings
    from persistence.pool import ConnectionPoolManager

    settings = ConnectionSettings(
        host="localhost",
        port=5432,
        database="test",
        user="tester",
        password="secret",
        min_pool_size=1,
        max_pool_size=1,
        connection_timeout_seconds=1.0,
    )
    manager = ConnectionPoolManager(settings)

    mock_pool = MagicMock()
    mock_pool.connection.side_effect = TimeoutError("pool exhausted")

    with patch.object(manager, "_pool", mock_pool):
        with pytest.raises(PersistenceConnectionError) as exc_info:
            with manager.acquire():
                pass

    assert exc_info.value.code == "PERS_CONNECTION"
