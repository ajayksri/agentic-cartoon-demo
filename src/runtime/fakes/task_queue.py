"""Task queue fakes for runtime contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from worker.fakes.task_queue import FakeTaskQueue as WorkerFakeTaskQueue


@dataclass
class FakeConnectionManager:
    """Redis connection manager stub with controllable ping."""

    ping_ok: bool = True
    ping_delay_seconds: float = 0.0
    ping_calls: int = 0
    closed: bool = False

    def ping(self) -> None:
        import time

        self.ping_calls += 1
        if self.ping_delay_seconds > 0:
            time.sleep(self.ping_delay_seconds)
        if not self.ping_ok:
            raise RuntimeError("redis unavailable")

    def close(self) -> None:
        self.closed = True


FakeTaskQueue = WorkerFakeTaskQueue

__all__ = ["FakeConnectionManager", "FakeTaskQueue"]
