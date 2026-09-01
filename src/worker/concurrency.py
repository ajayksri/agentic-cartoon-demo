"""Per-task-type concurrency pool (LLD §4.6)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Backpressure via concurrency limits — caps parallel
# LLM calls per stage so workers do not overwhelm providers or exhaust memory.
# GUARDRAIL: Capacity — per-stage concurrency caps prevent runaway agent/tool parallelism.

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from config.types import AgentId, AppConfig, TaskType
from task_queue.types import PendingDelivery

from .constants import COLLECT_CONCURRENCY_LIMIT


@dataclass(frozen=True, slots=True)
class ConcurrencySlot:
    task_type: TaskType
    acquired_at: datetime


class ConcurrencyPool:
    """Thread pool with per-TaskType semaphores."""

    def __init__(
        self,
        *,
        config: AppConfig,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._limits = self._build_limits()
        self._semaphores = {
            task_type: threading.Semaphore(limit)
            for task_type, limit in self._limits.items()
        }
        self._executor = ThreadPoolExecutor(max_workers=sum(self._limits.values()))

    def _build_limits(self) -> dict[TaskType, int]:
        return {
            TaskType.COLLECT: COLLECT_CONCURRENCY_LIMIT,
            TaskType.SELECT_TOPIC: self._config.get_worker_concurrency(
                AgentId.TOPIC_SELECTOR
            ),
            TaskType.GENERATE_SCENARIO: self._config.get_worker_concurrency(
                AgentId.SCENARIO_GENERATOR
            ),
            TaskType.REVIEW_SCENARIO: self._config.get_worker_concurrency(
                AgentId.CRITIC
            ),
        }

    def submit(
        self,
        fn: Callable[[PendingDelivery], None],
        delivery: PendingDelivery,
    ) -> None:
        self._executor.submit(fn, delivery)

    def acquire_blocking(self, task_type: TaskType) -> ConcurrencySlot:
        semaphore = self._semaphores[task_type]
        semaphore.acquire()
        return ConcurrencySlot(task_type=task_type, acquired_at=self._clock())

    def release(self, slot: ConcurrencySlot) -> None:
        self._semaphores[slot.task_type].release()

    def shutdown(self, *, wait: bool, timeout: float | None) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)
        if wait and timeout is not None:
            # ThreadPoolExecutor.shutdown does not accept timeout; best-effort wait.
            pass
