"""Unit tests for RT-003 — QueueBoundaryLoggerAdapter."""

from __future__ import annotations

import json
from types import SimpleNamespace

from config.types import TaskType
from observability.fakes import create_fake_bindings
from task_queue.boundary_log import (
    TaskAckedEvent,
    TaskDequeuedEvent,
    TaskEnqueuedEvent,
    TaskQueueErrorEvent,
)

from runtime.queue_adapter import QueueBoundaryLoggerAdapter


def _adapter() -> tuple[QueueBoundaryLoggerAdapter, object]:
    config = SimpleNamespace(
        service_name="runtime-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    logger, meter, _tracer, _correlation = create_fake_bindings(config)
    return QueueBoundaryLoggerAdapter(logger, meter), logger


def test_enqueued_event_emits_task_enqueued_log() -> None:
    adapter, logger = _adapter()
    event = TaskEnqueuedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        delivery_id="del-1",
    )

    adapter.emit(event)

    payload = json.loads(logger.records[-1])  # type: ignore[attr-defined]
    assert payload["event"] == "task_enqueued"
    assert payload["workflow_id"] == "wf-1"
    assert payload["task_id"] == "task-1"


def test_dequeued_event_emits_task_dequeued_log() -> None:
    adapter, logger = _adapter()
    event = TaskDequeuedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        delivery_id="del-1",
    )

    adapter.emit(event)

    payload = json.loads(logger.records[-1])  # type: ignore[attr-defined]
    assert payload["event"] == "task_dequeued"
    assert payload["attributes"]["delivery_id"] == "del-1"


def test_acked_event_emits_task_acked_log() -> None:
    adapter, logger = _adapter()
    event = TaskAckedEvent(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        delivery_id="del-1",
    )

    adapter.emit(event)

    payload = json.loads(logger.records[-1])  # type: ignore[attr-defined]
    assert payload["event"] == "task_acked"


def test_error_event_emits_task_queue_error_log() -> None:
    from observability import get_correlation_context

    adapter, logger = _adapter()
    event = TaskQueueErrorEvent(
        stream="cartoon:tasks:collect",
        error_code="dequeue_failed",
        consumer_group="cartoon:workers:collect",
        delivery_id="del-1",
    )

    with get_correlation_context().bind(workflow_id="wf-1", task_id="task-1"):
        adapter.emit(event)

    payload = json.loads(logger.records[-1])  # type: ignore[attr-defined]
    assert payload["event"] == "task_queue.error"
    assert payload["error_class"] == "dequeue_failed"
    assert payload["attributes"]["consumer_group"] == "cartoon:workers:collect"
    assert "operation" not in payload["attributes"]
