"""Fake task queue recording dequeue/ack order."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from task_queue.types import PendingDelivery


@dataclass
class FakeTaskQueue:
    """Records dequeue/ack order; thread-safe ack from pool threads."""

    pending: list[PendingDelivery] = field(default_factory=list)
    in_flight: list[PendingDelivery] = field(default_factory=list)
    acked: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def enqueue_delivery(self, delivery: PendingDelivery) -> None:
        with self._lock:
            self.pending.append(delivery)

    def ensure_consumer_group(self, stream: str, consumer_group: str) -> None:
        return None

    def dequeue(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        *,
        block_ms: int,
    ) -> PendingDelivery | None:
        with self._lock:
            if self.in_flight:
                return self.in_flight[0]
            if not self.pending:
                return None
            delivery = self.pending.pop(0)
            self.in_flight.append(delivery)
            return delivery

    def ack(self, delivery: PendingDelivery) -> None:
        with self._lock:
            self.acked.append(delivery.delivery_id)
            self.in_flight = [
                item for item in self.in_flight if item.delivery_id != delivery.delivery_id
            ]
