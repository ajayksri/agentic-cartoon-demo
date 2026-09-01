"""Driver exception translation to public PersistenceError subclasses."""

from __future__ import annotations

from psycopg import OperationalError
from psycopg.errors import InternalError, SerializationFailure

from persistence.errors import (
    PersistenceConflictError,
    PersistenceConnectionError,
    PersistenceError,
    PersistenceTransactionError,
)

_CONNECTION_CLASS_NAMES = frozenset(
    {
        "OperationalError",
        "InterfaceError",
        "ConnectionException",
        "ConnectionDoesNotExist",
        "ConnectionFailure",
        "ConnectionTimeout",
        "CannotConnectNow",
    }
)

_TRANSACTION_CLASS_NAMES = frozenset(
    {
        "InternalError",
        "InFailedSqlTransaction",
    }
)


class ErrorTranslator:
    def translate(
        self,
        exc: BaseException,
        *,
        operation: str,
        entity_id: str | None = None,
    ) -> PersistenceError:
        class_name = type(exc).__name__

        if isinstance(exc, SerializationFailure) or class_name == "SerializationFailure":
            return PersistenceConflictError(
                self._conflict_message(operation, entity_id)
            )

        if isinstance(exc, OperationalError) or class_name in _CONNECTION_CLASS_NAMES:
            return PersistenceConnectionError(
                self._connection_message(operation)
            )

        if self._is_transaction_failure(exc, operation, class_name):
            return PersistenceTransactionError(
                self._transaction_message(operation)
            )

        return PersistenceConnectionError(self._connection_message(operation))

    def _is_transaction_failure(
        self,
        exc: BaseException,
        operation: str,
        class_name: str,
    ) -> bool:
        message = str(exc).lower()
        if "commit" in message or "rollback" in message:
            return True
        if "commit" in operation or "rollback" in operation:
            if isinstance(exc, InternalError) or class_name in _TRANSACTION_CLASS_NAMES:
                return True
        return False

    def _connection_message(self, operation: str) -> str:
        return f"Persistence connection error during {operation}"

    def _conflict_message(self, operation: str, entity_id: str | None) -> str:
        if entity_id is not None:
            return f"Persistence conflict error during {operation} for entity {entity_id}"
        return f"Persistence conflict error during {operation}"

    def _transaction_message(self, operation: str) -> str:
        return f"Persistence transaction error during {operation}"
