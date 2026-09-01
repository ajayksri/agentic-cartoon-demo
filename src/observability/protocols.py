"""Public protocol definitions for the observability module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from .types import LogEnvelope, MetricDescriptor, SpanStatus, TraceContext


@runtime_checkable
class Counter(Protocol):
    """Counter instrument protocol."""

    def add(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        """Increment the counter by value with bounded labels."""


@runtime_checkable
class Histogram(Protocol):
    """Histogram instrument protocol."""

    def record(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        """Record an observation with bounded labels."""


@runtime_checkable
class Gauge(Protocol):
    """Gauge instrument protocol."""

    def set(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        """Set the gauge value with bounded labels."""


@runtime_checkable
class Span(Protocol):
    """Active trace span protocol."""

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        """Attach a bounded scalar attribute to the span."""

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        """Record a span event (e.g., retry, idempotency hit)."""

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        """Record exception metadata without secret leakage."""

    def end(self, status: SpanStatus = "OK") -> None:
        """Finalize the span."""

    def __enter__(self) -> Span:
        ...

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        ...


@runtime_checkable
class Logger(Protocol):
    """Structured logging protocol."""

    def emit(self, envelope: LogEnvelope) -> None:
        """Validate, redact, and emit a structured log envelope."""

    def debug(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        ...

    def info(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        ...

    def warning(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        ...

    def error(
        self,
        event: str,
        message: str,
        *,
        error_class: str,
        retryable: bool,
        **fields: str | int | float | bool,
    ) -> None:
        ...


@runtime_checkable
class Meter(Protocol):
    """Metrics registration and emission protocol."""

    def register_counter(self, descriptor: MetricDescriptor) -> Counter:
        ...

    def register_histogram(self, descriptor: MetricDescriptor) -> Histogram:
        ...

    def register_gauge(self, descriptor: MetricDescriptor) -> Gauge:
        ...


@runtime_checkable
class Tracer(Protocol):
    """Distributed tracing protocol."""

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Span:
        ...

    def current_trace_context(self) -> TraceContext | None:
        ...


@runtime_checkable
class CorrelationContext(Protocol):
    """Workflow/task correlation and trace propagation protocol."""

    @property
    def workflow_id(self) -> str | None:
        ...

    @property
    def task_id(self) -> str | None:
        ...

    @property
    def task_attempt(self) -> int | None:
        ...

    def bind(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> AbstractContextManager[None]:
        """Set correlation fields for the current async/task scope."""

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        """Write trace propagation fields into a carrier map."""

    def extract(self, carrier: Mapping[str, str]) -> TraceContext:
        """Parse trace context from a carrier map."""

    def attach(self, ctx: TraceContext) -> AbstractContextManager[None]:
        """Activate an extracted trace context for downstream spans."""
