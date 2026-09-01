"""Internal error message templates (MOD-WKR-INV-022)."""

from __future__ import annotations

from config.types import TaskType


def format_worker_message(
    *,
    code: str,
    message: str,
    workflow_id: str | None = None,
    task_id: str | None = None,
    task_type: TaskType | None = None,
) -> str:
    """Build a worker error message with bounded identifiers only."""
    parts = [f"code={code}", message]
    if workflow_id is not None:
        parts.append(f"workflow_id={workflow_id}")
    if task_id is not None:
        parts.append(f"task_id={task_id}")
    if task_type is not None:
        parts.append(f"task_type={task_type.value}")
    return " ".join(parts)


def handler_not_found_message(*, task_type: TaskType) -> str:
    return format_worker_message(
        code="WKR_NO_HANDLER",
        message="No handler registered for task type",
        task_type=task_type,
    )


def task_not_found_message(*, task_id: str) -> str:
    return format_worker_message(
        code="WKR_TASK_NOT_FOUND",
        message="Task record not found for queue message",
        task_id=task_id,
    )


def lease_conflict_message(*, task_id: str, worker_id: str) -> str:
    return format_worker_message(
        code="WKR_LEASE_CONFLICT",
        message="Lease held by another worker",
        task_id=task_id,
    ) + f" worker_id={worker_id}"


def idempotency_conflict_message(*, idempotency_key: str) -> str:
    return format_worker_message(
        code="WKR_IDEMPOTENCY",
        message="Unexpected idempotency state",
    ) + f" idempotency_key={idempotency_key}"


def execution_error_message(
    *,
    workflow_id: str,
    task_id: str,
    task_type: TaskType,
    detail: str,
) -> str:
    return format_worker_message(
        code="WKR_EXECUTION",
        message=detail,
        workflow_id=workflow_id,
        task_id=task_id,
        task_type=task_type,
    )


def retry_exhausted_message(
    *,
    workflow_id: str,
    task_id: str,
    task_type: TaskType,
    attempt: int,
) -> str:
    return format_worker_message(
        code="WKR_RETRY_EXHAUSTED",
        message=f"Retry budget exhausted at attempt {attempt}",
        workflow_id=workflow_id,
        task_id=task_id,
        task_type=task_type,
    )


def shutdown_message(*, detail: str) -> str:
    return format_worker_message(code="WKR_SHUTDOWN", message=detail)
