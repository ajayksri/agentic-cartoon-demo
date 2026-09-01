"""Unit tests for OBS-011 — LoggerImpl (CT-OBS-002, CT-OBS-005, CT-OBS-006)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO
from types import SimpleNamespace

import pytest

from observability.types import LogEnvelope, TraceContext


def _config(*, log_level: str = "DEBUG") -> object:
    from observability.settings import _ObservabilityConfig

    return _ObservabilityConfig(
        service_name="test-service",
        log_level=log_level,  # type: ignore[arg-type]
        strict_telemetry_errors=True,
    )


class _FakeCorrelation:
    def __init__(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> None:
        self._workflow_id = workflow_id
        self._task_id = task_id
        self._task_attempt = task_attempt

    @property
    def workflow_id(self) -> str | None:
        return self._workflow_id

    @property
    def task_id(self) -> str | None:
        return self._task_id

    @property
    def task_attempt(self) -> int | None:
        return self._task_attempt

    def bind(self, **kwargs: object):
        raise NotImplementedError

    def inject(self, carrier: object) -> None:
        raise NotImplementedError

    def extract(self, carrier: object) -> TraceContext:
        raise NotImplementedError

    def attach(self, ctx: TraceContext):
        raise NotImplementedError


class _FakeTracer:
    def __init__(self, trace_ctx: TraceContext | None = None) -> None:
        self._trace_ctx = trace_ctx

    def start_span(self, name: str, *, attributes: object = None):
        raise NotImplementedError

    def current_trace_context(self) -> TraceContext | None:
        return self._trace_ctx


def _build_logger(
    *,
    log_level: str = "DEBUG",
    correlation: _FakeCorrelation | None = None,
    tracer: _FakeTracer | None = None,
    output: StringIO | None = None,
):
    from observability.logger_impl import LoggerImpl

    buffer = output or StringIO()
    logger = LoggerImpl(
        config=_config(log_level=log_level),
        correlation=correlation or _FakeCorrelation(),
        tracer=tracer or _FakeTracer(),
        output=buffer,
    )
    return logger, buffer


def _base_envelope(**overrides: object) -> LogEnvelope:
    defaults: dict[str, object] = {
        "event": "workflow_created",
        "level": "INFO",
        "timestamp": datetime(2026, 8, 30, tzinfo=UTC),
        "message": "ok",
        "service_name": "test-service",
    }
    defaults.update(overrides)
    return LogEnvelope(**defaults)  # type: ignore[arg-type]


@pytest.mark.ct_obs("CT-OBS-002")
def test_workflow_created_serializes_workflow_id() -> None:
    """CT-OBS-002: workflow_created envelope JSON contains workflow_id."""
    logger, buffer = _build_logger()

    logger.emit(_base_envelope(event="workflow_created", workflow_id="wf-123"))

    line = buffer.getvalue()
    assert "wf-123" in line
    parsed = json.loads(line.strip())
    assert parsed["workflow_id"] == "wf-123"
    assert parsed["event"] == "workflow_created"


def test_emit_writes_compact_single_line_json() -> None:
    """Acceptance: one compact JSON line with no spaces after separators."""
    logger, buffer = _build_logger()

    logger.emit(_base_envelope(event="workflow_created", workflow_id="wf-1"))

    line = buffer.getvalue()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert ": " not in line
    json.loads(line.strip())


def test_emit_rejects_oversized_attribute_string() -> None:
    """LLD §8.3 step 5: oversized attribute rejected at LoggerImpl boundary."""
    from observability.errors import InvalidLogEnvelopeError

    logger, buffer = _build_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(
            _base_envelope(
                attributes={"payload": "x" * 1025},
            )
        )

    assert buffer.getvalue() == ""


def test_emit_rejects_non_scalar_attribute() -> None:
    """LLD §8.3 step 5: non-scalar attribute rejected at LoggerImpl boundary."""
    from observability.errors import InvalidLogEnvelopeError

    logger, buffer = _build_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(
            _base_envelope(
                attributes={"items": ["a", "b"]},  # type: ignore[dict-item]
            )
        )

    assert buffer.getvalue() == ""


@pytest.mark.ct_obs("CT-OBS-005")
def test_error_envelope_missing_fields_raises() -> None:
    """CT-OBS-005: ERROR envelope without error_class/retryable raises."""
    from observability.errors import InvalidLogEnvelopeError

    logger, buffer = _build_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(
            _base_envelope(
                event="task_failed",
                level="ERROR",
                error_class=None,
                retryable=None,
            )
        )

    assert buffer.getvalue() == ""


def test_error_convenience_method_includes_required_fields() -> None:
    """Logger.error with required kwargs emits valid ERROR envelope."""
    logger, buffer = _build_logger()

    logger.error(
        "task_failed",
        "task failed",
        error_class="ProviderError",
        retryable=True,
        workflow_id="wf-1",
        task_id="task-1",
    )

    parsed = json.loads(buffer.getvalue().strip())
    assert parsed["level"] == "ERROR"
    assert parsed["error_class"] == "ProviderError"
    assert parsed["retryable"] is True


@pytest.mark.ct_obs("CT-OBS-006")
def test_secret_in_message_scrubbed() -> None:
    """CT-OBS-006: secret-like message content is scrubbed in output."""
    logger, buffer = _build_logger()

    logger.emit(
        _base_envelope(
            event="general_event",
            message="prefix sk-abcdefghijklmnopqrstuvwxyz123456 suffix",
        )
    )

    line = buffer.getvalue()
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in line
    assert "[REDACTED:api_key]" in line


@pytest.mark.ct_obs("CT-OBS-006")
def test_unredactable_secret_raises() -> None:
    """CT-OBS-006: entirely secret message raises RedactionRequiredError."""
    from observability.errors import RedactionRequiredError

    logger, buffer = _build_logger()

    with pytest.raises(RedactionRequiredError):
        logger.emit(
            _base_envelope(
                event="general_event",
                message="sk-abcdefghijklmnopqrstuvwxyz1234567890",
            )
        )

    assert buffer.getvalue() == ""


def test_below_level_log_filtered_without_output() -> None:
    """Implementation test: DEBUG below INFO min_level produces no I/O."""
    logger, buffer = _build_logger(log_level="INFO")

    logger.emit(_base_envelope(level="DEBUG", workflow_id="wf-1"))

    assert buffer.getvalue() == ""


def test_correlation_merge_non_destructive_caller_wins() -> None:
    """Implementation test: explicit envelope workflow_id wins over correlation."""
    correlation = _FakeCorrelation(workflow_id="wf-correlation")
    logger, buffer = _build_logger(correlation=correlation)

    logger.emit(_base_envelope(workflow_id="wf-caller"))

    parsed = json.loads(buffer.getvalue().strip())
    assert parsed["workflow_id"] == "wf-caller"


def test_trace_merge_non_destructive_caller_wins() -> None:
    """Implementation test: explicit trace_id wins over active trace context."""
    tracer = _FakeTracer(
        TraceContext(trace_id="trace-from-tracer", span_id="span-from-tracer")
    )
    logger, buffer = _build_logger(tracer=tracer)

    logger.emit(
        _base_envelope(
            workflow_id="wf-1",
            trace_id="trace-from-caller",
            span_id="span-from-caller",
        )
    )

    parsed = json.loads(buffer.getvalue().strip())
    assert parsed["trace_id"] == "trace-from-caller"
    assert parsed["span_id"] == "span-from-caller"


def test_trace_merge_fills_missing_from_tracer() -> None:
    """Implementation test: missing trace fields filled from tracer context."""
    tracer = _FakeTracer(
        TraceContext(trace_id="trace-from-tracer", span_id="span-from-tracer")
    )
    logger, buffer = _build_logger(tracer=tracer)

    logger.info("workflow_created", "created", workflow_id="wf-1")

    parsed = json.loads(buffer.getvalue().strip())
    assert parsed["trace_id"] == "trace-from-tracer"
    assert parsed["span_id"] == "span-from-tracer"


def test_build_envelope_sets_service_name_from_config() -> None:
    """Implementation test: convenience methods use config.service_name."""
    logger, buffer = _build_logger()

    logger.info("workflow_created", "created", workflow_id="wf-1")

    parsed = json.loads(buffer.getvalue().strip())
    assert parsed["service_name"] == "test-service"


def test_injectable_output_avoids_stdout_mutation(
    strict_telemetry_settings: SimpleNamespace,
) -> None:
    """Acceptance: injectable output stream used instead of sys.stdout."""
    assert strict_telemetry_settings.service_name == "test-service"

    from observability.logger_impl import LoggerImpl
    from observability.settings import _ObservabilityConfig
    from observability.validation import default_validation_pipelines

    buffer = StringIO()
    config = _ObservabilityConfig(
        service_name=strict_telemetry_settings.service_name,
        log_level=strict_telemetry_settings.log_level,
        strict_telemetry_errors=strict_telemetry_settings.strict_telemetry_errors,
    )
    logger = LoggerImpl(
        config=config,
        correlation=_FakeCorrelation(),
        tracer=_FakeTracer(),
        pipelines=default_validation_pipelines(),
        output=buffer,
    )

    logger.emit(_base_envelope(workflow_id="wf-injected"))
    assert "wf-injected" in buffer.getvalue()
