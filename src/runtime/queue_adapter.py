"""Queue boundary event adapter — maps task_queue events to observability logs."""

from __future__ import annotations

from observability.protocols import Logger, Meter

from task_queue.boundary_log import (
    QueueBoundaryEvent,
    TaskAckedEvent,
    TaskDequeuedEvent,
    TaskEnqueuedEvent,
    TaskQueueErrorEvent,
)


class QueueBoundaryLoggerAdapter:
    """Implements QueueBoundaryLogger protocol via structural typing."""

    def __init__(self, logger: Logger, meter: Meter) -> None:
        self._logger = logger
        self._meter = meter

    def emit(self, event: QueueBoundaryEvent) -> None:
        if isinstance(event, TaskEnqueuedEvent):
            self._logger.info(
                "task_enqueued",
                "Task enqueued",
                workflow_id=event.workflow_id,
                task_id=event.task_id,
                task_type=event.task_type.value,
                stream=event.stream,
            )
            return

        if isinstance(event, TaskDequeuedEvent):
            self._logger.info(
                "task_dequeued",
                "Task dequeued",
                workflow_id=event.workflow_id,
                task_id=event.task_id,
                task_type=event.task_type.value,
                stream=event.stream,
                delivery_id=event.delivery_id,
            )
            return

        if isinstance(event, TaskAckedEvent):
            self._logger.info(
                "task_acked",
                "Task acked",
                workflow_id=event.workflow_id,
                task_id=event.task_id,
                delivery_id=event.delivery_id,
            )
            return

        if isinstance(event, TaskQueueErrorEvent):
            from observability import get_correlation_context

            correlation = get_correlation_context()
            workflow_id = correlation.workflow_id or event.delivery_id or "unknown"
            task_id = correlation.task_id or event.delivery_id or "unknown"
            self._logger.error(
                "task_queue.error",
                "Task queue error",
                workflow_id=workflow_id,
                task_id=task_id,
                error_class=event.error_code,
                retryable=True,
                stream=event.stream,
                **(
                    {"consumer_group": event.consumer_group}
                    if event.consumer_group is not None
                    else {}
                ),
            )
