"""Pre-code test mold for OBS-004 — log and trace validation pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from observability.types import LogEnvelope


def _base_envelope(**overrides: object) -> LogEnvelope:
    defaults: dict[str, object] = {
        "event": "general_event",
        "level": "INFO",
        "timestamp": datetime(2026, 8, 30, tzinfo=timezone.utc),
        "message": "ok",
        "service_name": "test-service",
    }
    defaults.update(overrides)
    return LogEnvelope(**defaults)  # type: ignore[arg-type]


@pytest.mark.ct_obs("CT-OBS-003")
def test_task_started_without_task_id_raises(
    strict_telemetry_settings: SimpleNamespace,
) -> None:
    """CT-OBS-003: task_started without task_id raises InvalidLogEnvelopeError."""
    assert strict_telemetry_settings.strict_telemetry_errors is True

    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import validate_event_class_requirements

    envelope = _base_envelope(
        event="task_started",
        workflow_id="wf-1",
        task_id=None,
    )

    with pytest.raises(InvalidLogEnvelopeError):
        validate_event_class_requirements(envelope)


@pytest.mark.ct_obs("CT-OBS-004")
def test_task_retried_without_task_attempt_raises(
    strict_telemetry_settings: SimpleNamespace,
) -> None:
    """CT-OBS-004: task_retried without task_attempt raises InvalidLogEnvelopeError."""
    assert strict_telemetry_settings.strict_telemetry_errors is True

    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import validate_event_class_requirements

    envelope = _base_envelope(
        event="task_retried",
        workflow_id="wf-1",
        task_id="task-1",
        task_attempt=None,
    )

    with pytest.raises(InvalidLogEnvelopeError):
        validate_event_class_requirements(envelope)


@pytest.mark.ct_obs("CT-OBS-005")
def test_error_level_without_error_fields_raises(
    strict_telemetry_settings: SimpleNamespace,
) -> None:
    """CT-OBS-005: ERROR level without error_class/retryable raises InvalidLogEnvelopeError."""
    assert strict_telemetry_settings.strict_telemetry_errors is True

    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import validate_error_envelope_fields

    envelope = _base_envelope(
        level="ERROR",
        error_class=None,
        retryable=None,
    )

    with pytest.raises(InvalidLogEnvelopeError):
        validate_error_envelope_fields(envelope)


@pytest.mark.ct_obs("CT-OBS-007")
def test_prompt_attribute_rejected_by_forbidden_log_fields(
    strict_telemetry_settings: SimpleNamespace,
) -> None:
    """CT-OBS-007: prompt in envelope.attributes is rejected."""
    assert strict_telemetry_settings.strict_telemetry_errors is True

    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import check_forbidden_log_fields

    envelope = _base_envelope(attributes={"prompt": "user input must not appear in logs"})

    with pytest.raises(InvalidLogEnvelopeError):
        check_forbidden_log_fields(envelope)


@pytest.mark.parametrize(
    ("event", "expected_class"),
    [
        ("workflow_started", "WORKFLOW"),
        ("state_transition_completed", "WORKFLOW"),
        ("task_started", "TASK"),
        ("provider_call_failed", "TASK"),
        ("task_retried", "RETRYABLE_LIFECYCLE"),
        ("task_redelivered", "RETRYABLE_LIFECYCLE"),
        ("general_event", "GENERAL"),
    ],
)
def test_classify_event_returns_correct_class(event: str, expected_class: str) -> None:
    """classify_event returns correct class for workflow/task/retryable/general prefixes."""
    from observability.validation import EventClass, classify_event

    assert classify_event(event) is EventClass[expected_class]


def test_task_retried_classified_as_retryable_not_task() -> None:
    """task_retried is RETRYABLE_LIFECYCLE, not TASK, despite task_ prefix."""
    from observability.validation import EventClass, classify_event

    assert classify_event("task_retried") is EventClass.RETRYABLE_LIFECYCLE
    assert classify_event("task_retried") is not EventClass.TASK


def test_default_validation_pipelines_wires_module_callables() -> None:
    """default_validation_pipelines returns module-level function references."""
    import observability.validation as validation

    pipelines = validation.default_validation_pipelines()

    assert pipelines.merge_correlation_fields is validation.merge_correlation_fields
    assert pipelines.check_forbidden_log_fields is validation.check_forbidden_log_fields
    assert pipelines.validate_event_class_requirements is validation.validate_event_class_requirements
    assert pipelines.validate_error_envelope_fields is validation.validate_error_envelope_fields
    assert pipelines.validate_bounded_attributes is validation.validate_bounded_attributes
    assert pipelines.passes_log_level_filter is validation.passes_log_level_filter
    assert pipelines.redact_log_envelope is validation.redact_log_envelope
    assert pipelines.run_log_validation_pipeline is validation.run_log_validation_pipeline


def test_envelope_to_json_dict_omits_none_and_formats_timestamp() -> None:
    """envelope_to_json_dict omits None fields and uses ISO-8601 timestamps."""
    from observability.validation import envelope_to_json_dict

    ts = datetime(2026, 8, 30, 12, 30, 45, tzinfo=timezone.utc)
    envelope = _base_envelope(
        timestamp=ts,
        workflow_id="wf-1",
        task_id=None,
        attributes={"region": "us-east-1", "count": 3},
    )

    result = envelope_to_json_dict(envelope)

    assert "task_id" not in result
    assert result["timestamp"] == "2026-08-30T12:30:45+00:00"
    assert result["workflow_id"] == "wf-1"
    assert result["attributes"] == {"region": "us-east-1", "count": 3}


def test_validate_bounded_attributes_rejects_long_string() -> None:
    """validate_bounded_attributes rejects strings exceeding 1024 characters."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import validate_bounded_attributes

    with pytest.raises(InvalidLogEnvelopeError):
        validate_bounded_attributes({"detail": "x" * 1025})


def test_validate_bounded_attributes_rejects_non_scalar() -> None:
    """validate_bounded_attributes rejects non-scalar attribute values."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import validate_bounded_attributes

    with pytest.raises(InvalidLogEnvelopeError):
        validate_bounded_attributes({"items": ["a", "b"]})


def test_check_forbidden_trace_keys_rejects_forbidden_key() -> None:
    """check_forbidden_trace_keys rejects forbidden trace attribute keys."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import check_forbidden_trace_keys

    with pytest.raises(InvalidLogEnvelopeError):
        check_forbidden_trace_keys({"request_body": "payload"})


def test_enforce_bounded_trace_scalar_rejects_long_string() -> None:
    """enforce_bounded_trace_scalar rejects strings exceeding 1024 characters."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.validation import enforce_bounded_trace_scalar

    with pytest.raises(InvalidLogEnvelopeError):
        enforce_bounded_trace_scalar("detail", "x" * 1025)


def test_merge_correlation_fields_fills_absent_without_overwriting() -> None:
    """merge_correlation_fields fills absent fields without overwriting caller values."""
    from observability.validation import merge_correlation_fields

    correlation = SimpleNamespace(workflow_id="corr-wf", task_id="corr-task", task_attempt=2)
    tracer = SimpleNamespace(
        current_trace_context=lambda: SimpleNamespace(
            trace_id="trace-from-tracer",
            span_id="span-from-tracer",
        )
    )
    envelope = _base_envelope(
        workflow_id="caller-wf",
        task_id=None,
        trace_id=None,
        span_id="caller-span",
    )

    merged = merge_correlation_fields(envelope, correlation, tracer)  # type: ignore[arg-type]

    assert merged.workflow_id == "caller-wf"
    assert merged.task_id == "corr-task"
    assert merged.task_attempt == 2
    assert merged.trace_id == "trace-from-tracer"
    assert merged.span_id == "caller-span"


def test_run_log_validation_pipeline_returns_none_below_min_level() -> None:
    """run_log_validation_pipeline returns None when envelope is below min level."""
    from observability.validation import run_log_validation_pipeline

    correlation = SimpleNamespace(workflow_id=None, task_id=None, task_attempt=None)
    tracer = SimpleNamespace(current_trace_context=lambda: None)
    envelope = _base_envelope(level="DEBUG")

    result = run_log_validation_pipeline(
        envelope,
        correlation=correlation,  # type: ignore[arg-type]
        tracer=tracer,  # type: ignore[arg-type]
        min_level="INFO",
    )

    assert result is None
