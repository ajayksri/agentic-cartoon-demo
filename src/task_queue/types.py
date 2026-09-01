"""Public type definitions for the task queue module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from config.types import TaskType

# W3C trace propagation keys aligned with observability interfaces §4.
TRACE_CARRIER_KEY_TRACEPARENT = "traceparent"
TRACE_CARRIER_KEY_TRACESTATE = "tracestate"


@dataclass(frozen=True, slots=True)
class TaskMessage:
    """Slim task envelope for internal queue transport (ACD-FR-045)."""

    task_id: str
    workflow_id: str
    task_type: TaskType
    attempt: int
    created_at: datetime
    payload_reference: str
    trace_carrier: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    """Result of a successful enqueue operation."""

    delivery_id: str
    enqueued_at: datetime


@dataclass(frozen=True, slots=True)
class PendingDelivery:
    """Dequeued message pending ACK."""

    message: TaskMessage
    stream: str
    consumer_group: str
    delivery_id: str
    dequeued_at: datetime


@dataclass(frozen=True, slots=True)
class QueueStats:
    """Queue depth introspection for backpressure observability (ACD-FR-024)."""

    depth: int
    oldest_message_age_seconds: float
