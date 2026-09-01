"""Unit tests for OBS-006 — correlation context implementation."""

from __future__ import annotations

import pytest


@pytest.mark.ct_obs("CT-OBS-016")
def test_bind_workflow_id_visible_inside_scope_restored_outside() -> None:
    """CT-OBS-016: bind(workflow_id=...) is visible inside scope and restored outside."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.correlation import CorrelationContextImpl

    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())

    assert ctx.workflow_id is None

    with ctx.bind(workflow_id="wf-1"):
        assert ctx.workflow_id == "wf-1"

    assert ctx.workflow_id is None


def test_nested_bind_pushes_and_pops_stack_correctly() -> None:
    """Nested bind scopes push/pop the correlation stack without leaking fields."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.correlation import CorrelationContextImpl

    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())

    with ctx.bind(workflow_id="wf-outer"):
        assert ctx.workflow_id == "wf-outer"
        assert ctx.task_id is None

        with ctx.bind(task_id="task-inner"):
            assert ctx.workflow_id == "wf-outer"
            assert ctx.task_id == "task-inner"

        assert ctx.workflow_id == "wf-outer"
        assert ctx.task_id is None

    assert ctx.workflow_id is None
    assert ctx.task_id is None


def test_partial_field_merge_on_bind_retains_existing_fields() -> None:
    """bind with only task_id retains an existing workflow_id from outer scope."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.correlation import CorrelationContextImpl

    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())

    with ctx.bind(workflow_id="wf-1"):
        with ctx.bind(task_id="task-1"):
            assert ctx.workflow_id == "wf-1"
            assert ctx.task_id == "task-1"


@pytest.mark.ct_obs("CT-OBS-012")
def test_correlation_inject_extract_round_trip() -> None:
    """CorrelationContextImpl inject/extract delegates to propagation helpers."""
    from opentelemetry import context, trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.correlation import CorrelationContextImpl

    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())
    span_context = SpanContext(
        trace_id=int(trace_id, 16),
        span_id=int(span_id, 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    otel_context = trace.set_span_in_context(NonRecordingSpan(span_context))
    token = context.attach(otel_context)
    carrier: dict[str, str] = {}

    try:
        ctx.inject(carrier)
    finally:
        context.detach(token)

    extracted = ctx.extract(carrier)

    assert extracted.trace_id == trace_id
    assert extracted.span_id == span_id


def test_attach_sets_and_restores_otel_span_context() -> None:
    """attach integrates with OTel context API and restores prior context on exit."""
    from opentelemetry import trace
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.correlation import CorrelationContextImpl
    from observability.types import TraceContext

    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    remote = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=1,
        is_remote=True,
    )

    prior = trace.get_current_span().get_span_context()

    with ctx.attach(remote):
        active = trace.get_current_span().get_span_context()
        assert format(active.trace_id, "032x") == trace_id
        assert format(active.span_id, "016x") == span_id

    restored = trace.get_current_span().get_span_context()
    assert restored.trace_id == prior.trace_id
    assert restored.span_id == prior.span_id


def test_extract_malformed_carrier_raises_invalid_trace_context_error() -> None:
    """CorrelationContextImpl.extract propagates InvalidTraceContextError."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    from observability.errors import InvalidTraceContextError
    from observability.correlation import CorrelationContextImpl

    ctx = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())

    with pytest.raises(InvalidTraceContextError):
        ctx.extract({"traceparent": "not-a-valid-traceparent"})
