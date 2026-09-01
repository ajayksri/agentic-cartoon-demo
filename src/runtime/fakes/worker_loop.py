"""Worker loop spy for runtime contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeWorkerLoop:
    """Records stop() invocations for shutdown ordering tests (RT-TC-017)."""

    run_calls: int = 0
    stop_calls: int = 0

    def run(self) -> None:
        self.run_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1
