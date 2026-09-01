"""In-memory TaskQueue fake for contract tests (TQ-010, LLD §9.2)."""

from __future__ import annotations

from datetime import datetime, timezone

from config.types import TaskType

from task_queue import (
    AckError,
    EnqueueResult,
    InvalidTaskMessageError,
    PendingDelivery,
    QueueStats,
    TaskMessage,
)


class InMemoryTaskQueue:
    """Protocol-compliant fake with per-stream deque + PEL dict.

    Per-stream deque + PEL dict simulating consumer groups.
    Does not prove Redis redelivery (TQ-TC-003 requires integration or fakeredis).
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, TaskMessage]] = {}
        self._stream_order: dict[str, list[str]] = {}
        self._groups: set[tuple[str, str]] = set()
        self._group_next_index: dict[tuple[str, str], int] = {}
        self._pel: dict[tuple[str, str], dict[str, PendingDelivery]] = {}
        self._delivery_counter = 0

    def enqueue(self, stream: str, message: TaskMessage) -> EnqueueResult:
        self._validate_message(message)

        delivery_id = self._next_delivery_id()
        if stream not in self._entries:
            self._entries[stream] = {}
            self._stream_order[stream] = []
        self._entries[stream][delivery_id] = message
        self._stream_order[stream].append(delivery_id)

        return EnqueueResult(
            delivery_id=delivery_id,
            enqueued_at=datetime.now(timezone.utc),
        )

    def dequeue(
        self,
        stream: str,
        *,
        consumer_group: str,
        consumer_name: str,
        block_ms: int | None = None,
    ) -> PendingDelivery | None:
        del block_ms, consumer_name
        self._require_group(stream, consumer_group)

        pel = self._pel.setdefault((stream, consumer_group), {})
        if pel:
            delivery_id = next(iter(pel))
            return pel[delivery_id]

        order = self._stream_order.get(stream, [])
        index = self._group_next_index.get((stream, consumer_group), 0)
        while index < len(order):
            delivery_id = order[index]
            index += 1
            self._group_next_index[(stream, consumer_group)] = index

            message = self._entries[stream][delivery_id]
            self._validate_message(message)
            delivery = PendingDelivery(
                message=message,
                stream=stream,
                consumer_group=consumer_group,
                delivery_id=delivery_id,
                dequeued_at=datetime.now(timezone.utc),
            )
            pel[delivery_id] = delivery
            return delivery

        return None

    def ack(self, delivery: PendingDelivery) -> None:
        pel = self._pel.get((delivery.stream, delivery.consumer_group), {})
        if delivery.delivery_id not in pel:
            raise AckError(
                f"ACK failed for delivery_id '{delivery.delivery_id}': "
                "delivery not found or already acknowledged",
                delivery_id=delivery.delivery_id,
            )
        del pel[delivery.delivery_id]

    def ensure_consumer_group(
        self,
        stream: str,
        group: str,
        *,
        start_id: str = "0",
    ) -> None:
        del start_id
        self._groups.add((stream, group))
        self._pel.setdefault((stream, group), {})
        self._group_next_index.setdefault((stream, group), 0)

    def get_queue_stats(self, stream: str) -> QueueStats:
        depth = 0
        created_at_values: list[datetime] = []

        order = self._stream_order.get(stream, [])
        for (s, _), index in self._group_next_index.items():
            if s != stream:
                continue
            undelivered = max(0, len(order) - index)
            depth += undelivered
            for delivery_id in order[index:]:
                created_at_values.append(self._entries[stream][delivery_id].created_at)

        for (s, _), pel in self._pel.items():
            if s != stream:
                continue
            depth += len(pel)
            for delivery in pel.values():
                created_at_values.append(delivery.message.created_at)

        if depth == 0:
            return QueueStats(depth=0, oldest_message_age_seconds=0.0)

        oldest = min(created_at_values)
        now = datetime.now(timezone.utc)
        age = max(0.0, (now - oldest).total_seconds())
        return QueueStats(depth=depth, oldest_message_age_seconds=age)

    def dequeue_corrupt_entry_for_test(
        self,
        stream: str,
        *,
        consumer_group: str,
        consumer_name: str,
        missing_field: str,
    ) -> PendingDelivery:
        """Inject a corrupt entry and attempt dequeue (contract test seam)."""
        del consumer_name
        self._require_group(stream, consumer_group)

        delivery_id = self._next_delivery_id()
        field_values: dict[str, object] = {
            "task_id": "corrupt-task",
            "workflow_id": "wf-1",
            "task_type": TaskType.COLLECT,
            "attempt": 1,
            "created_at": datetime.now(timezone.utc),
            "payload_reference": "ref://corrupt",
        }
        if missing_field == "workflow_id":
            field_values["workflow_id"] = ""
        elif missing_field == "task_id":
            field_values["task_id"] = ""
        elif missing_field == "payload_reference":
            field_values["payload_reference"] = ""
        elif missing_field == "attempt":
            field_values["attempt"] = 0
        elif missing_field == "created_at":
            field_values["created_at"] = datetime(2026, 1, 1, 0, 0, 0)

        corrupt = TaskMessage(**field_values)  # type: ignore[arg-type]

        if stream not in self._entries:
            self._entries[stream] = {}
            self._stream_order[stream] = []
        self._entries[stream][delivery_id] = corrupt
        self._stream_order[stream].append(delivery_id)

        return self.dequeue(
            stream,
            consumer_group=consumer_group,
            consumer_name="worker-1",
            block_ms=0,
        )  # type: ignore[return-value]

    def _next_delivery_id(self) -> str:
        self._delivery_counter += 1
        return f"{self._delivery_counter}-0"

    def _require_group(self, stream: str, group: str) -> None:
        if (stream, group) not in self._groups:
            self.ensure_consumer_group(stream, group)

    def _validate_message(self, message: TaskMessage) -> None:
        missing: list[str] = []
        for field_name in ("task_id", "workflow_id", "payload_reference"):
            value = getattr(message, field_name)
            if value is None or not str(value).strip():
                missing.append(field_name)
        if message.attempt < 1:
            missing.append("attempt")
        if message.created_at.tzinfo is None:
            missing.append("created_at")
        if missing:
            raise InvalidTaskMessageError(
                f"Invalid task message: missing or invalid fields: {', '.join(missing)}",
                missing_fields=tuple(missing),
            )
