"""Pre-code test mold for PERS-004 — PostgresTransactionManager (LLD §3.2)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from persistence import PersistenceTransactionError


def test_nested_transaction_raises_transaction_error() -> None:
    """Nested transaction() enter → PersistenceTransactionError (CG-PERS-HLD-003)."""
    from persistence.transaction import PostgresTransactionManager

    pool_manager = MagicMock()

    @contextmanager
    def _fake_acquire():
        conn = MagicMock()
        yield conn

    pool_manager.acquire = _fake_acquire
    manager = PostgresTransactionManager(pool_manager)

    with manager.transaction():
        with pytest.raises(PersistenceTransactionError) as exc_info:
            with manager.transaction():
                pass

    assert exc_info.value.code == "PERS_TX"


def test_successful_scope_commits() -> None:
    """Clean exit commits and clears active session."""
    from persistence.session import get_active_session
    from persistence.transaction import PostgresTransactionManager

    pool_manager = MagicMock()
    conn = MagicMock()

    @contextmanager
    def _fake_acquire():
        yield conn

    pool_manager.acquire = _fake_acquire
    manager = PostgresTransactionManager(pool_manager)

    with manager.transaction():
        scope = get_active_session()
        assert scope is not None
        assert scope.in_transaction is True

    conn.commit.assert_called_once()
    assert get_active_session() is None


def test_exceptional_scope_rolls_back() -> None:
    """Exception inside scope rolls back and re-raises."""
    from persistence.session import get_active_session
    from persistence.transaction import PostgresTransactionManager

    pool_manager = MagicMock()
    conn = MagicMock()

    @contextmanager
    def _fake_acquire():
        yield conn

    pool_manager.acquire = _fake_acquire
    manager = PostgresTransactionManager(pool_manager)

    with pytest.raises(RuntimeError, match="boom"):
        with manager.transaction():
            raise RuntimeError("boom")

    conn.rollback.assert_called_once()
    assert get_active_session() is None
