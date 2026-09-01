"""Public task queue error types."""

from __future__ import annotations


class TaskQueueError(Exception):
    """Base class for all task queue module errors."""

    code: str = "TQ_ERROR"


class TaskQueueConnectionError(TaskQueueError):
    """Redis unreachable or authentication failed."""

    code = "TQ_CONN"


class TaskQueueUnavailableError(TaskQueueError):
    """Redis degraded or operation timed out."""

    code = "TQ_UNAVAILABLE"


class InvalidTaskMessageError(TaskQueueError):
    """Task envelope missing or invalid required fields."""

    code = "TQ_INVALID_MESSAGE"

    def __init__(self, message: str, *, missing_fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields


class ConsumerGroupError(TaskQueueError):
    """Consumer group create or read failure."""

    code = "TQ_CONSUMER_GROUP"

    def __init__(self, message: str, *, stream: str, group: str) -> None:
        super().__init__(message)
        self.stream = stream
        self.group = group


class AckError(TaskQueueError):
    """ACK failed for unknown or already-ACKed delivery."""

    code = "TQ_ACK"

    def __init__(self, message: str, *, delivery_id: str) -> None:
        super().__init__(message)
        self.delivery_id = delivery_id


class StreamNotFoundError(TaskQueueError):
    """Target stream does not exist."""

    code = "TQ_STREAM"

    def __init__(self, message: str, *, stream: str) -> None:
        super().__init__(message)
        self.stream = stream
