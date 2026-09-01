"""Public persistence error types."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for all persistence module errors."""

    code: str = "PERS_ERROR"


class PersistenceConnectionError(PersistenceError):
    """Database unreachable or connection pool exhausted."""

    code = "PERS_CONNECTION"


class PersistenceNotFoundError(PersistenceError):
    """Requested entity does not exist."""

    code = "PERS_NOT_FOUND"


class PersistenceConflictError(PersistenceError):
    """Optimistic concurrency conflict on workflow state update."""

    code = "PERS_CONFLICT"


class PersistenceDuplicateError(PersistenceError):
    """Duplicate idempotency or uniqueness violation."""

    code = "PERS_DUPLICATE"


class PersistenceLeaseConflictError(PersistenceError):
    """Active task lease held by another worker."""

    code = "PERS_LEASE"


class PersistenceImmutableError(PersistenceError):
    """Attempt to mutate committed immutable data."""

    code = "PERS_IMMUTABLE"


class PersistenceTransactionError(PersistenceError):
    """Transaction commit or rollback failure."""

    code = "PERS_TX"


class PersistenceValidationError(PersistenceError):
    """Required record field missing or invalid at repository boundary."""

    code = "PERS_VALIDATION"
