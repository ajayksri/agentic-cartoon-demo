"""Pre-code test mold for PRV-011 — ProviderTelemetry (LLD §4.10, §13)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest

from config.types import ProviderId
from providers.errors import ProviderRateLimitError
from providers.types import TokenUsage
_PROMPT_TEXT = "super-secret-prompt-body-do-not-log"
_RESPONSE_TEXT = "super-secret-response-body-do-not-log"
@contextmanager
def _observability_fakes() -> Iterator[tuple[object, object, object]]:
    from observability import get_correlation_context
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from observability.fakes import CapturingMeter, InMemoryLogger, RecordingTracer
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="providers-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    with get_correlation_context().bind(
        workflow_id="wf-test",
        task_id="task-test",
        task_attempt=1,
    ):
        yield InMemoryLogger, CapturingMeter, RecordingTracer
    _reset_observability_state()
def test_recording_telemetry_captures_emit_call_started() -> None:
    from providers.telemetry import RecordingTelemetry

    with _observability_fakes():
        telemetry = RecordingTelemetry(provider_id=ProviderId.OPENAI)
        span = telemetry.emit_call_started(model="gpt-4o-mini")

    assert len(telemetry.call_started) == 1
    assert telemetry.call_started[0]["model"] == "gpt-4o-mini"
    assert span is not None
def test_recording_telemetry_captures_success_completion() -> None:
    from providers.telemetry import RecordingTelemetry

    with _observability_fakes():
        telemetry = RecordingTelemetry(provider_id=ProviderId.OPENAI)
        span = telemetry.emit_call_started(model="gpt-4o-mini")
        telemetry.emit_call_completed(
            model="gpt-4o-mini",
            latency_ms=12.5,
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
            span=span,
        )

    assert len(telemetry.call_completed) == 1
    assert telemetry.call_completed[0]["latency_ms"] == 12.5
def test_pre_vendor_failure_emits_failed_with_zero_latency_and_no_span() -> None:
    from providers.telemetry import RecordingTelemetry

    with _observability_fakes():
        telemetry = RecordingTelemetry(provider_id=ProviderId.OPENAI)
        error = ProviderRateLimitError("client rate limit")
        telemetry.emit_call_failed(
            model="gpt-4o-mini",
            error=error,
            latency_ms=0.0,
            span=None,
        )

    assert len(telemetry.call_failed) == 1
    assert telemetry.call_failed[0]["latency_ms"] == 0.0
    assert telemetry.call_failed[0]["span"] is None
@pytest.mark.prv_tc("060")
def test_failed_call_logs_omit_prompt_and_response_text() -> None:
    from observability import get_logger
    from providers.telemetry import ProviderTelemetry

    with _observability_fakes():
        telemetry = ProviderTelemetry(provider_id=ProviderId.OPENAI)
        error = ProviderRateLimitError(
            f"classified failure unrelated to {_PROMPT_TEXT}"
        )
        telemetry.emit_call_failed(
            model="gpt-4o-mini",
            error=error,
            latency_ms=1.0,
            span=telemetry.emit_call_started(model="gpt-4o-mini"),
        )
        records = "\n".join(get_logger().records)

    assert _PROMPT_TEXT not in records
    assert _RESPONSE_TEXT not in records
def test_instruments_not_registered_at_import_time() -> None:
    """CG-PRV-HLD-003: histogram/counter registration is lazy on first generate."""
    import providers.telemetry as telemetry_module

    assert not hasattr(telemetry_module, "_instruments_registered_at_import")

    from providers.telemetry import ProviderTelemetry

    with _observability_fakes():
        telemetry = ProviderTelemetry(provider_id=ProviderId.OPENAI)
        telemetry.emit_call_started(model="gpt-4o-mini")

    assert telemetry._duration_histogram is not None  # type: ignore[attr-defined]
