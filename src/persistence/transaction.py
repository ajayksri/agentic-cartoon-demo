"""PostgreSQL unit-of-work transaction manager."""

# DISTRIBUTED-SYSTEMS SHOWCASE: ACID transactions — workflow state, artifacts,
# idempotency records, and outbox rows commit or roll back together.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from persistence.errors import PersistenceTransactionError
from persistence.errors_internal import ErrorTranslator
from persistence.pool import ConnectionPoolManager
from persistence.session import SessionScope, _active_session, get_active_session, set_active_session


class PostgresTransactionManager:
    def __init__(self, pool_manager: ConnectionPoolManager) -> None:
        self._pool_manager = pool_manager
        self._error_translator = ErrorTranslator()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        active = get_active_session()
        if active is not None and active.in_transaction:
            raise PersistenceTransactionError("Nested transaction not supported")

        with self._pool_manager.acquire() as connection:
            connection.execute("BEGIN")
            token = set_active_session(SessionScope(connection, in_transaction=True))
            try:
                try:
                    yield
                except Exception:
                    self._rollback(connection)
                    raise
                else:
                    self._commit(connection)
            finally:
                _active_session.reset(token)

    def is_in_transaction(self) -> bool:
        active = get_active_session()
        return active is not None and active.in_transaction

    def _commit(self, connection: object) -> None:
        try:
            connection.commit()  # type: ignore[attr-defined]
        except Exception as exc:
            raise self._error_translator.translate(exc, operation="commit") from exc

    def _rollback(self, connection: object) -> None:
        try:
            connection.rollback()  # type: ignore[attr-defined]
        except Exception as exc:
            raise self._error_translator.translate(exc, operation="rollback") from exc
