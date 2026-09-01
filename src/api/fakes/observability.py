"""Observability doubles for API contract tests."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager, nullcontext

from observability.fakes import InMemoryLogger, RecordingTracer
from observability.types import TraceContext


class FakeCorrelationContext:
    """Trace extract/inject assertions for contract tests."""

    def __init__(self) -> None:
        self.injected: list[dict[str, str]] = []
        self.extracted: list[Mapping[str, str]] = []
        self._workflow_id: str | None = None

    @property
    def workflow_id(self) -> str | None:
        return self._workflow_id

    @property
    def task_id(self) -> str | None:
        return None

    @property
    def task_attempt(self) -> int | None:
        return None

    def bind(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> AbstractContextManager[None]:
        del task_id, task_attempt
        self._workflow_id = workflow_id
        return nullcontext()

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        self.injected.append(dict(carrier))

    def extract(self, carrier: Mapping[str, str]) -> TraceContext:
        self.extracted.append(dict(carrier))
        return TraceContext(trace_id="0" * 32, span_id="0" * 16, is_remote=True)

    def attach(self, ctx: TraceContext) -> AbstractContextManager[None]:
        del ctx
        return nullcontext()


RecordingLogger = InMemoryLogger
RecordingTracer = RecordingTracer
