"""Public worker error types."""

from __future__ import annotations

from config.types import TaskType


class WorkerError(Exception):
    """Base class for all worker module errors."""

    code: str = "WKR_ERROR"


class HandlerNotFoundError(WorkerError):
    """No TaskHandler registered for the requested task type."""

    code = "WKR_NO_HANDLER"

    def __init__(self, message: str, *, task_type: TaskType) -> None:
        super().__init__(message)
        self.task_type = task_type


class DuplicateHandlerError(WorkerError):
    """Attempt to register two handlers for the same task type."""

    code = "WKR_DUPLICATE_HANDLER"

    def __init__(self, message: str, *, task_type: TaskType) -> None:
        super().__init__(message)
        self.task_type = task_type


class TaskRecordNotFoundError(WorkerError):
    """Queue message references a task row that does not exist."""

    code = "WKR_TASK_NOT_FOUND"

    def __init__(self, message: str, *, task_id: str) -> None:
        super().__init__(message)
        self.task_id = task_id


class LeaseConflictError(WorkerError):
    """Another worker holds the active lease for this task."""

    code = "WKR_LEASE_CONFLICT"

    def __init__(self, message: str, *, task_id: str, worker_id: str) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.worker_id = worker_id


class IdempotencyConflictError(WorkerError):
    """Unexpected idempotency state during orchestration."""

    code = "WKR_IDEMPOTENCY"

    def __init__(self, message: str, *, idempotency_key: str) -> None:
        super().__init__(message)
        self.idempotency_key = idempotency_key


class TaskExecutionError(WorkerError):
    """Unclassified task handler execution failure."""

    code = "WKR_EXECUTION"

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str,
        task_id: str,
        task_type: TaskType,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.task_type = task_type
        self.retryable = retryable


class RetryExhaustedError(WorkerError):
    """Retry budget exhausted for a task."""

    code = "WKR_RETRY_EXHAUSTED"

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str,
        task_id: str,
        task_type: TaskType,
        attempt: int,
    ) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.task_id = task_id
        self.task_type = task_type
        self.attempt = attempt


class WorkerShutdownError(WorkerError):
    """Worker loop stopped while mandatory work remained incomplete."""

    code = "WKR_SHUTDOWN"

    def __init__(self, message: str) -> None:
        super().__init__(message)
