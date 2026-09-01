"""W3C traceparent/tracestate inject/extract helpers (internal — not public surface)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Distributed tracing — W3C trace context propagates
# across API, coordinator, worker, and provider calls for end-to-end request visibility.

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import TYPE_CHECKING

from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from observability.errors import InvalidTraceContextError
from observability.types import TraceContext

if TYPE_CHECKING:
    from opentelemetry.context import Context

_TRACEPARENT_KEY = "traceparent"
_TRACESTATE_KEY = "tracestate"

_TRACEPARENT_PATTERN = re.compile(
    r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$",
    re.IGNORECASE,
)


def _normalize_carrier(carrier: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in carrier.items()}


def _validate_traceparent(traceparent: str) -> None:
    if not _TRACEPARENT_PATTERN.match(traceparent):
        raise InvalidTraceContextError(f"Malformed traceparent: {traceparent!r}")


def inject_trace_context(
    carrier: MutableMapping[str, str],
    *,
    propagator: TraceContextTextMapPropagator,
) -> None:
    temp: dict[str, str] = {}
    propagator.inject(temp, context.get_current())
    for key, value in temp.items():
        carrier[key.lower()] = value


def extract_trace_context(
    carrier: Mapping[str, str],
    *,
    propagator: TraceContextTextMapPropagator,
) -> TraceContext:
    """Raise InvalidTraceContextError on missing/malformed traceparent."""
    normalized = _normalize_carrier(carrier)

    traceparent = normalized.get(_TRACEPARENT_KEY)
    if traceparent is None:
        raise InvalidTraceContextError("Missing traceparent in carrier")

    _validate_traceparent(traceparent)

    try:
        otel_ctx = propagator.extract(normalized)
    except Exception as exc:
        raise InvalidTraceContextError(
            f"Failed to extract trace context: {exc}"
        ) from exc

    span_context = trace.get_current_span(otel_ctx).get_span_context()
    if not span_context.is_valid:
        raise InvalidTraceContextError("Invalid span context extracted from carrier")

    return otel_span_context_to_trace_context(span_context, is_remote=True)


def otel_span_context_to_trace_context(
    span_context: SpanContext,
    *,
    is_remote: bool = False,
) -> TraceContext:
    return TraceContext(
        trace_id=format(span_context.trace_id, "032x"),
        span_id=format(span_context.span_id, "016x"),
        trace_flags=int(span_context.trace_flags),
        is_remote=is_remote,
    )


def trace_context_to_otel_context(ctx: TraceContext) -> Context:
    span_context = SpanContext(
        trace_id=int(ctx.trace_id, 16),
        span_id=int(ctx.span_id, 16),
        is_remote=ctx.is_remote,
        trace_flags=TraceFlags(ctx.trace_flags),
    )
    return trace.set_span_in_context(NonRecordingSpan(span_context))
