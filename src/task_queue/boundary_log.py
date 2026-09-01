"""Queue boundary event types and logger protocol (LLD §2.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from config.types import TaskType


@dataclass(frozen=True, slots=True)
class TaskEnqueuedEvent:
    workflow_id: str
    task_id: str
    task_type: TaskType
    stream: str
    delivery_id: str


@dataclass(frozen=True, slots=True)
class TaskDequeuedEvent:
    workflow_id: str
    task_id: str
    task_type: TaskType
    stream: str
    consumer_group: str
    delivery_id: str


@dataclass(frozen=True, slots=True)
class TaskAckedEvent:
    workflow_id: str
    task_id: str
    task_type: TaskType
    stream: str
    consumer_group: str
    delivery_id: str


@dataclass(frozen=True, slots=True)
class TaskQueueErrorEvent:
    stream: str
    error_code: str
    consumer_group: str | None = None
    delivery_id: str | None = None


QueueBoundaryEvent = (
    TaskEnqueuedEvent
    | TaskDequeuedEvent
    | TaskAckedEvent
    | TaskQueueErrorEvent
)


class QueueBoundaryLogger(Protocol):
    def emit(self, event: QueueBoundaryEvent) -> None: ...


class NoOpQueueBoundaryLogger:
    def emit(self, event: QueueBoundaryEvent) -> None:
        return None
