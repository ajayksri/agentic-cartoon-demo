"""Unit tests for WKR-001 message templates (MOD-WKR-INV-022)."""

from __future__ import annotations

from config.types import TaskType

from worker.constants import FORBIDDEN_LOG_FIELDS
from worker.messages import (
    execution_error_message,
    format_worker_message,
    handler_not_found_message,
    lease_conflict_message,
    retry_exhausted_message,
    shutdown_message,
    task_not_found_message,
)


def test_format_worker_message_bounded_fields() -> None:
    msg = format_worker_message(
        code="WKR_TEST",
        message="detail",
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
    )
    assert "code=WKR_TEST" in msg
    assert "workflow_id=wf-1" in msg
    assert "task_id=task-1" in msg
    assert "task_type=COLLECT" in msg


def test_message_templates_exclude_forbidden_substrings() -> None:
    samples = [
        handler_not_found_message(task_type=TaskType.COLLECT),
        task_not_found_message(task_id="task-1"),
        lease_conflict_message(task_id="task-1", worker_id="worker-1"),
        execution_error_message(
            workflow_id="wf-1",
            task_id="task-1",
            task_type=TaskType.COLLECT,
            detail="execution failed",
        ),
        retry_exhausted_message(
            workflow_id="wf-1",
            task_id="task-1",
            task_type=TaskType.COLLECT,
            attempt=3,
        ),
        shutdown_message(detail="graceful stop"),
    ]
    for msg in samples:
        for forbidden in FORBIDDEN_LOG_FIELDS:
            assert forbidden not in msg
