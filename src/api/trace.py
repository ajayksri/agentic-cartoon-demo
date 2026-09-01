"""W3C trace context ingress and egress helpers."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING

from observability import get_logger

from .telemetry import get_active_correlation_context, get_active_tracer
from observability.errors import InvalidTraceContextError

if TYPE_CHECKING:
    from observability.protocols import CorrelationContext
    from observability.types import TraceContext


class TraceExtractor:
    """Ingress W3C trace context and egress header injection."""

    def __init__(self, correlation_context: CorrelationContext | None = None) -> None:
        self._correlation_context = correlation_context or get_active_correlation_context()
        self._tracer = get_active_tracer()

    @contextmanager
    def request_scope(
        self, headers: Mapping[str, str]
    ) -> AbstractContextManager[TraceContext | None]:
        remote_ctx = self.extract_from_headers(headers)
        if remote_ctx is None:
            yield None
        else:
            with self._correlation_context.attach(remote_ctx):
                yield remote_ctx

    def extract_from_headers(self, headers: Mapping[str, str]) -> TraceContext | None:
        normalized = {key.lower(): value for key, value in headers.items()}
        if "traceparent" not in normalized:
            return None
        try:
            return self._correlation_context.extract(normalized)
        except InvalidTraceContextError:
            get_logger().warning(
                "invalid_trace_context",
                "Invalid or malformed trace context in request headers",
            )
            return None

    def inject_response_headers(self, carrier: MutableMapping[str, str]) -> None:
        if self._tracer.current_trace_context() is not None:
            self._correlation_context.inject(carrier)

    def current_trace_id(self) -> str | None:
        ctx = self._tracer.current_trace_context()
        return ctx.trace_id if ctx is not None else None
