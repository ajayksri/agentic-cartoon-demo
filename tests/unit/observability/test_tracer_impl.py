"""Pre-code test mold for OBS-010 — TracerImpl / SpanImpl (CT-OBS-014, CT-OBS-015)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

_ENTIRELY_SECRET_VALUE = "sk-abcdefghijklmnopqrstuvwxyz1234567890"


def _build_tracer(*, strict: bool = True):
    from observability.correlation import CorrelationContextImpl
    from observability.settings import _ObservabilityConfig
    from observability.tracer_impl import TracerImpl

    config = _ObservabilityConfig(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=strict,
    )
    correlation = CorrelationContextImpl(propagator=MagicMock())
    otel_tracer = MagicMock()
    return TracerImpl(config=config, correlation=correlation, otel_tracer=otel_tracer), otel_tracer


def _make_otel_context(*, trace_id: int, span_id: int):
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    span_context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return trace.set_span_in_context(NonRecordingSpan(span_context))


def _attach_otel_context(*, trace_id: int, span_id: int):
    from opentelemetry import context

    otel_context = _make_otel_context(trace_id=trace_id, span_id=span_id)
    token = context.attach(otel_context)
    return otel_context, token


@pytest.mark.ct_obs("CT-OBS-015")
def test_ct_obs_015_forbidden_trace_attribute_keys_raise() -> None:
    """CT-OBS-015: Forbidden trace keys raise InvalidLogEnvelopeError at boundary."""
    from observability.errors import InvalidLogEnvelopeError

    tracer, _otel_tracer = _build_tracer()

    with pytest.raises(InvalidLogEnvelopeError):
        tracer.start_span("provider_call_test", attributes={"prompt": "secret content"})


@pytest.mark.ct_obs("CT-OBS-015")
def test_ct_obs_015_provider_allowed_attributes_accepted() -> None:
    """CT-OBS-015: Provider span allowed keys pass validation at start_span."""
    tracer, otel_tracer = _build_tracer()

    span = tracer.start_span(
        "provider_call_openai",
        attributes={
            "provider": "openai",
            "model": "gpt-4",
            "status": "ok",
            "error_class": "none",
            "retryable": False,
        },
    )

    assert span is not None
    otel_tracer.start_span.assert_not_called()


def test_otel_span_created_only_on_enter_not_start_span() -> None:
    """LLD §6.5: OTel span created on __enter__, not at start_span."""
    from opentelemetry import context

    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    parent_ctx, parent_token = _attach_otel_context(
        trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
        span_id=0x00F067AA0BA902B7,
    )

    try:
        span = tracer.start_span("workflow.step", attributes={"status": "running"})
        otel_tracer.start_span.assert_not_called()

        with span:
            otel_tracer.start_span.assert_called_once_with(
                "workflow.step",
                context=parent_ctx,
                attributes={"status": "running"},
            )
    finally:
        context.detach(parent_token)


def test_start_span_captures_parent_context_at_call_time_not_enter() -> None:
    """Parent context snapshot at start_span survives OTel context mutation before __enter__."""
    from opentelemetry import context

    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    original_ctx, original_token = _attach_otel_context(
        trace_id=0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA,
        span_id=0xBBBBBBBBBBBBBBBB,
    )
    mutated_ctx = _make_otel_context(
        trace_id=0xCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC,
        span_id=0xDDDDDDDDDDDDDDDD,
    )

    try:
        span = tracer.start_span("child.operation")
        mutation_token = context.attach(mutated_ctx)
        try:
            assert context.get_current() is not original_ctx
            with span:
                otel_tracer.start_span.assert_called_once_with(
                    "child.operation",
                    context=original_ctx,
                    attributes={},
                )
        finally:
            context.detach(mutation_token)
    finally:
        context.detach(original_token)


def test_span_context_manager_attaches_and_detaches_once() -> None:
    """LLD §6.5: __enter__ attaches OTel context; __exit__ detaches with returned token."""
    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with (
        patch("observability.tracer_impl.context.attach", return_value="attach-token") as mock_attach,
        patch("observability.tracer_impl.context.detach") as mock_detach,
    ):
        with tracer.start_span("scoped.operation") as span:
            assert span is not None

        mock_attach.assert_called_once()
        mock_detach.assert_called_once_with("attach-token")


@pytest.mark.ct_obs("CT-OBS-014")
def test_ct_obs_014_distinct_retry_events_recordable() -> None:
    """CT-OBS-014: Retry events remain distinct (unit-level span event recording)."""
    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with tracer.start_span("task.execute") as span:
        span.add_event("retry", attributes={"task_attempt": 1})
        span.add_event("retry", attributes={"task_attempt": 2})

    assert mock_otel_span.add_event.call_count == 2
    assert mock_otel_span.add_event.call_args_list == [
        call("retry", attributes={"task_attempt": 1}),
        call("retry", attributes={"task_attempt": 2}),
    ]


def test_add_event_merges_correlation_with_caller_precedence() -> None:
    """add_event merges correlation fields; caller-supplied keys win on conflict."""
    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with tracer._correlation.bind(workflow_id="wf-1", task_id="task-1", task_attempt=2):
        with tracer.start_span("task.execute") as span:
            span.add_event(
                "retry",
                attributes={"task_attempt": 99, "status": "retrying"},
            )

    mock_otel_span.add_event.assert_called_once_with(
        "retry",
        attributes={
            "task_attempt": 99,
            "status": "retrying",
            "workflow_id": "wf-1",
            "task_id": "task-1",
        },
    )


def test_record_exception_sets_attributes_and_error_status() -> None:
    """record_exception sets normalized error attributes and OTel ERROR status."""
    from opentelemetry import trace

    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with tracer.start_span("task.execute") as span:
        span.record_exception("ProviderTimeout", retryable=True)

    mock_otel_span.set_attribute.assert_any_call("error_class", "ProviderTimeout")
    mock_otel_span.set_attribute.assert_any_call("retryable", True)
    error_status_calls = [
        call_args
        for call_args in mock_otel_span.set_status.call_args_list
        if call_args.args[0].status_code == trace.StatusCode.ERROR
    ]
    assert error_status_calls


def test_set_attribute_rejects_forbidden_keys() -> None:
    """Provider policy: prompt/response attributes rejected on set_attribute."""
    from observability.errors import InvalidLogEnvelopeError

    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with tracer.start_span("provider_call_test", attributes={"provider": "openai"}) as span:
        with pytest.raises(InvalidLogEnvelopeError):
            span.set_attribute("response", "model output")


def test_add_event_rejects_forbidden_keys() -> None:
    """Forbidden trace keys raise InvalidLogEnvelopeError on add_event boundary."""
    from observability.errors import InvalidLogEnvelopeError

    tracer, otel_tracer = _build_tracer()
    mock_otel_span = MagicMock()
    otel_tracer.start_span.return_value = mock_otel_span

    with tracer.start_span("provider_call_test", attributes={"provider": "openai"}) as span:
        with pytest.raises(InvalidLogEnvelopeError):
            span.add_event("provider_response", attributes={"prompt": "secret content"})


@pytest.mark.parametrize(
    "invoke",
    [
        pytest.param(
            lambda tracer: tracer.start_span(
                "test",
                attributes={"status": _ENTIRELY_SECRET_VALUE},
            ),
            id="start_span",
        ),
        pytest.param(
            lambda tracer: _invoke_set_attribute_with_secret(tracer),
            id="set_attribute",
        ),
        pytest.param(
            lambda tracer: _invoke_add_event_with_secret(tracer),
            id="add_event",
        ),
    ],
)
def test_trace_attribute_redaction_required_raises(invoke) -> None:
    """Unredactable secret values raise RedactionRequiredError at trace boundary."""
    from observability.errors import RedactionRequiredError

    tracer, _otel_tracer = _build_tracer()

    with pytest.raises(RedactionRequiredError):
        invoke(tracer)


def _invoke_set_attribute_with_secret(tracer) -> None:
    mock_otel_span = MagicMock()
    tracer._otel_tracer.start_span.return_value = mock_otel_span
    with tracer.start_span("test", attributes={"provider": "openai"}) as span:
        span.set_attribute("status", _ENTIRELY_SECRET_VALUE)


def _invoke_add_event_with_secret(tracer) -> None:
    mock_otel_span = MagicMock()
    tracer._otel_tracer.start_span.return_value = mock_otel_span
    with tracer.start_span("test", attributes={"provider": "openai"}) as span:
        span.add_event("event", attributes={"status": _ENTIRELY_SECRET_VALUE})
