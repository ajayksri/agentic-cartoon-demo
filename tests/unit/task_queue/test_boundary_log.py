"""Smoke tests for TQ-002 — boundary event types (LLD §2.3)."""

from __future__ import annotations

from config.types import TaskType
from task_queue.boundary_log import (
    NoOpQueueBoundaryLogger,
    TaskAckedEvent,
    TaskDequeuedEvent,
    TaskEnqueuedEvent,
    TaskQueueErrorEvent,
)


def test_boundary_event_dataclasses_instantiate() -> None:
    TaskEnqueuedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        delivery_id="1-0",
    )
    TaskDequeuedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        delivery_id="1-0",
    )
    TaskAckedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        delivery_id="1-0",
    )
    TaskQueueErrorEvent(
        stream="cartoon:tasks:collect",
        error_code="TQ_INVALID_MESSAGE",
        consumer_group="cartoon:workers:collect",
        delivery_id="1-0",
    )


def test_noop_boundary_logger_emit_is_noop() -> None:
    logger = NoOpQueueBoundaryLogger()
    logger.emit(
        TaskEnqueuedEvent(
            workflow_id="wf-1",
            task_id="task-1",
            task_type=TaskType.COLLECT,
            stream="cartoon:tasks:collect",
            delivery_id="1-0",
        )
    )
