"""Pre-code test mold for OBS-005 — W3C trace context propagation."""

from __future__ import annotations

import pytest

VALID_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
VALID_SPAN_ID = "00f067aa0ba902b7"


@pytest.mark.ct_obs("CT-OBS-012")
def test_valid_traceparent_round_trips_through_inject_extract() -> None:
    """CT-OBS-012: inject then extract preserves trace_id and span_id."""
    from opentelemetry import context, trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.propagation import extract_trace_context, inject_trace_context

    propagator = TraceContextTextMapPropagator()
    span_context = SpanContext(
        trace_id=int(VALID_TRACE_ID, 16),
        span_id=int(VALID_SPAN_ID, 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    otel_context = trace.set_span_in_context(NonRecordingSpan(span_context))
    token = context.attach(otel_context)
    carrier: dict[str, str] = {}

    try:
        inject_trace_context(carrier, propagator=propagator)
    finally:
        context.detach(token)

    extracted = extract_trace_context(carrier, propagator=propagator)

    assert extracted.trace_id == VALID_TRACE_ID
    assert extracted.span_id == VALID_SPAN_ID


@pytest.mark.ct_obs("CT-OBS-013")
def test_malformed_traceparent_raises_invalid_trace_context_error() -> None:
    """CT-OBS-013: malformed traceparent raises InvalidTraceContextError."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.errors import InvalidTraceContextError
    from observability.propagation import extract_trace_context

    carrier = {"traceparent": "not-a-valid-traceparent"}
    propagator = TraceContextTextMapPropagator()

    with pytest.raises(InvalidTraceContextError):
        extract_trace_context(carrier, propagator=propagator)


def test_missing_traceparent_raises_invalid_trace_context_error() -> None:
    """extract_trace_context raises InvalidTraceContextError when traceparent is absent."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.errors import InvalidTraceContextError
    from observability.propagation import extract_trace_context

    propagator = TraceContextTextMapPropagator()

    with pytest.raises(InvalidTraceContextError, match="Missing traceparent"):
        extract_trace_context({}, propagator=propagator)


def test_extract_accepts_case_insensitive_carrier_keys() -> None:
    """extract_trace_context accepts mixed-case traceparent carrier keys."""
    from opentelemetry import context, trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.propagation import extract_trace_context, inject_trace_context

    propagator = TraceContextTextMapPropagator()
    span_context = SpanContext(
        trace_id=int(VALID_TRACE_ID, 16),
        span_id=int(VALID_SPAN_ID, 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    otel_context = trace.set_span_in_context(NonRecordingSpan(span_context))
    token = context.attach(otel_context)
    injected: dict[str, str] = {}

    try:
        inject_trace_context(injected, propagator=propagator)
    finally:
        context.detach(token)

    assert "traceparent" in injected
    mixed_case_carrier = {"Traceparent": injected["traceparent"]}

    extracted = extract_trace_context(mixed_case_carrier, propagator=propagator)

    assert extracted.trace_id == VALID_TRACE_ID
    assert extracted.span_id == VALID_SPAN_ID


def test_extract_sets_is_remote_true() -> None:
    """extract_trace_context marks extracted TraceContext as remote."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.propagation import extract_trace_context

    propagator = TraceContextTextMapPropagator()
    carrier = {"traceparent": f"00-{VALID_TRACE_ID}-{VALID_SPAN_ID}-01"}

    extracted = extract_trace_context(carrier, propagator=propagator)

    assert extracted.is_remote is True


def test_otel_span_context_to_trace_context_preserves_is_remote_flag() -> None:
    """otel_span_context_to_trace_context preserves the is_remote flag."""
    from opentelemetry.trace import SpanContext, TraceFlags

    from observability.propagation import otel_span_context_to_trace_context

    span_context = SpanContext(
        trace_id=int(VALID_TRACE_ID, 16),
        span_id=int(VALID_SPAN_ID, 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )

    local_ctx = otel_span_context_to_trace_context(span_context, is_remote=False)
    remote_ctx = otel_span_context_to_trace_context(span_context, is_remote=True)

    assert local_ctx.is_remote is False
    assert remote_ctx.is_remote is True
    assert local_ctx.trace_id == VALID_TRACE_ID
    assert local_ctx.span_id == VALID_SPAN_ID
