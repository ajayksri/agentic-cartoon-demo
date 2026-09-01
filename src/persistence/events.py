"""Internal operation-logging event shapes and no-op logger/recorder defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PersistenceOperationEvent:
    operation: str
    error_code: str | None = None
    entity_id: str | None = None


class OperationLogger(Protocol):
    def log_operation(self, event: PersistenceOperationEvent) -> None: ...


class NoOpOperationLogger:
    def log_operation(self, event: PersistenceOperationEvent) -> None:
        return None


class MetricsRecorder(Protocol):
    def increment(self, operation: str, result: str) -> None: ...


class NoOpMetricsRecorder:
    def increment(self, operation: str, result: str) -> None:
        return None
