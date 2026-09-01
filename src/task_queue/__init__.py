"""Task queue module public surface."""

from __future__ import annotations

from .errors import (
    AckError,
    ConsumerGroupError,
    InvalidTaskMessageError,
    StreamNotFoundError,
    TaskQueueConnectionError,
    TaskQueueError,
    TaskQueueUnavailableError,
)
from .protocols import TaskQueue
from .types import (
    TRACE_CARRIER_KEY_TRACEPARENT,
    TRACE_CARRIER_KEY_TRACESTATE,
    EnqueueResult,
    PendingDelivery,
    QueueStats,
    TaskMessage,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "AckError",
    "ConsumerGroupError",
    "EnqueueResult",
    "InvalidTaskMessageError",
    "PendingDelivery",
    "QueueStats",
    "StreamNotFoundError",
    "TRACE_CARRIER_KEY_TRACEPARENT",
    "TRACE_CARRIER_KEY_TRACESTATE",
    "TaskMessage",
    "TaskQueue",
    "TaskQueueConnectionError",
    "TaskQueueError",
    "TaskQueueUnavailableError",
    "create_task_queue",
]


from .factory import create_task_queue
