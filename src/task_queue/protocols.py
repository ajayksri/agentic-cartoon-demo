"""Public protocol definitions for the task queue module contract boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import EnqueueResult, PendingDelivery, QueueStats, TaskMessage


@runtime_checkable
class TaskQueue(Protocol):
    """Redis Streams-backed task transport abstraction (ACD-INT-007)."""

    def enqueue(self, stream: str, message: TaskMessage) -> EnqueueResult:
        """Append a validated task message to the target stream."""

    def dequeue(
        self,
        stream: str,
        *,
        consumer_group: str,
        consumer_name: str,
        block_ms: int | None = None,
    ) -> PendingDelivery | None:
        """Read the next pending message for a consumer group member."""

    def ack(self, delivery: PendingDelivery) -> None:
        """Acknowledge successful processing of a dequeued delivery."""

    def ensure_consumer_group(
        self,
        stream: str,
        group: str,
        *,
        start_id: str = "0",
    ) -> None:
        """Create a consumer group on the stream if absent (idempotent)."""

    def get_queue_stats(self, stream: str) -> QueueStats:
        """Return queue depth and oldest-message age for backpressure observability."""
