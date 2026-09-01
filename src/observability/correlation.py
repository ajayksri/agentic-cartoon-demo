"""Contextvars-backed correlation context implementation (internal — not public surface)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Cross-service correlation — workflow_id, task_id, and
# attempt number attach to every log and span for debugging multi-step agent runs.

from __future__ import annotations

import contextvars
from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

from opentelemetry import context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from observability.propagation import (
    extract_trace_context,
    inject_trace_context,
    trace_context_to_otel_context,
)
from observability.types import TraceContext

CorrelationScope = AbstractContextManager[None]


@dataclass(frozen=True, slots=True)
class _CorrelationSnapshot:
    workflow_id: str | None
    task_id: str | None
    task_attempt: int | None


_EMPTY_SNAPSHOT = _CorrelationSnapshot(None, None, None)

_correlation_stack: contextvars.ContextVar[tuple[_CorrelationSnapshot, ...]] = (
    contextvars.ContextVar("_correlation_stack", default=())
)


def _merge_snapshot(
    current: _CorrelationSnapshot,
    *,
    workflow_id: str | None,
    task_id: str | None,
    task_attempt: int | None,
) -> _CorrelationSnapshot:
    return _CorrelationSnapshot(
        workflow_id=workflow_id if workflow_id is not None else current.workflow_id,
        task_id=task_id if task_id is not None else current.task_id,
        task_attempt=task_attempt if task_attempt is not None else current.task_attempt,
    )


@contextmanager
def _push_snapshot(snapshot: _CorrelationSnapshot) -> AbstractContextManager[None]:
    current_stack = _correlation_stack.get()
    token = _correlation_stack.set(current_stack + (snapshot,))
    try:
        yield None
    finally:
        _correlation_stack.reset(token)


class CorrelationContextImpl:
    def __init__(self, *, propagator: TraceContextTextMapPropagator) -> None:
        self._propagator = propagator

    @property
    def workflow_id(self) -> str | None:
        return self.active_snapshot().workflow_id

    @property
    def task_id(self) -> str | None:
        return self.active_snapshot().task_id

    @property
    def task_attempt(self) -> int | None:
        return self.active_snapshot().task_attempt

    def bind(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> CorrelationScope:
        merged = _merge_snapshot(
            self.active_snapshot(),
            workflow_id=workflow_id,
            task_id=task_id,
            task_attempt=task_attempt,
        )
        return _push_snapshot(merged)

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        inject_trace_context(carrier, propagator=self._propagator)

    def extract(self, carrier: Mapping[str, str]) -> TraceContext:
        return extract_trace_context(carrier, propagator=self._propagator)

    def attach(self, ctx: TraceContext) -> CorrelationScope:
        return _attach_trace_context(ctx)

    def active_snapshot(self) -> _CorrelationSnapshot:
        stack = _correlation_stack.get()
        if not stack:
            return _EMPTY_SNAPSHOT
        return stack[-1]


@contextmanager
def _attach_trace_context(ctx: TraceContext) -> AbstractContextManager[None]:
    otel_ctx = trace_context_to_otel_context(ctx)
    token = context.attach(otel_ctx)
    try:
        yield None
    finally:
        context.detach(token)
