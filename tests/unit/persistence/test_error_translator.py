"""Pre-code test mold for PERS-002 — ErrorTranslator (LLD §3.4, §6)."""

from __future__ import annotations

from psycopg import OperationalError
from psycopg.errors import InternalError, SerializationFailure

from persistence import (
    PersistenceConflictError,
    PersistenceConnectionError,
    PersistenceTransactionError,
)

_FORBIDDEN_MESSAGE_FRAGMENTS = (
    "password=",
    "postgresql://",
    "jsonb",
    "sk-",
    '{"secret"',
)

_EXCEPTION_TYPES: dict[str, type[BaseException]] = {
    "OperationalError": OperationalError,
    "SerializationFailure": SerializationFailure,
    "InternalError": InternalError,
}


def _make_psycopg_exception(class_name: str, message: str = "driver error") -> BaseException:
    """Synthetic psycopg exception with recognizable class for translator mapping."""
    exc_type = _EXCEPTION_TYPES.get(class_name)
    if exc_type is None:
        exc_type = type(class_name, (Exception,), {})
    return exc_type(message)


def test_operational_error_maps_to_connection_error() -> None:
    """OperationalError / connection failure → PersistenceConnectionError (PERS_CONNECTION)."""
    from persistence.errors_internal import ErrorTranslator

    exc = _make_psycopg_exception(
        "OperationalError",
        "connection to server failed password=secret",
    )
    translator = ErrorTranslator()

    result = translator.translate(exc, operation="health_check")

    assert isinstance(result, PersistenceConnectionError)
    assert result.code == "PERS_CONNECTION"


def test_serialization_failure_maps_to_conflict_error() -> None:
    """SerializationFailure → PersistenceConflictError (PERS_CONFLICT)."""
    from persistence.errors_internal import ErrorTranslator

    exc = _make_psycopg_exception("SerializationFailure", "could not serialize access")
    translator = ErrorTranslator()

    result = translator.translate(exc, operation="update_workflow_state", entity_id="wf-1")

    assert isinstance(result, PersistenceConflictError)
    assert result.code == "PERS_CONFLICT"


def test_commit_failure_maps_to_transaction_error() -> None:
    """Commit/rollback failure → PersistenceTransactionError (PERS_TX)."""
    from persistence.errors_internal import ErrorTranslator

    exc = _make_psycopg_exception("InternalError", "commit failed")
    translator = ErrorTranslator()

    result = translator.translate(exc, operation="transaction_commit")

    assert isinstance(result, PersistenceTransactionError)
    assert result.code == "PERS_TX"


def test_rollback_failure_maps_to_transaction_error() -> None:
    """Rollback failure → PersistenceTransactionError (PERS_TX)."""
    from persistence.errors_internal import ErrorTranslator

    exc = _make_psycopg_exception("InternalError", "rollback failed")
    translator = ErrorTranslator()

    result = translator.translate(exc, operation="transaction_rollback")

    assert isinstance(result, PersistenceTransactionError)
    assert result.code == "PERS_TX"


def test_translated_message_omits_credentials_and_jsonb() -> None:
    """PERS-TC-071 / MOD-PERS-INV-019: messages omit secrets and raw JSONB."""
    from persistence.errors_internal import ErrorTranslator

    exc = _make_psycopg_exception(
        "OperationalError",
        'INSERT failed body={"api_key":"sk-live"} password=hunter2 '
        "dsn=postgresql://user:pass@localhost/db",
    )
    translator = ErrorTranslator()

    result = translator.translate(exc, operation="insert_artifact", entity_id="art-1")
    message = str(result).lower()

    for fragment in _FORBIDDEN_MESSAGE_FRAGMENTS:
        assert fragment not in message
