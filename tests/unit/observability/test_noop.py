"""Unit tests for OBS-012 — NoOp implementations (CT-OBS-003–008, CT-OBS-018)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from observability.protocols import (
    CorrelationContext,
    Counter,
    Gauge,
    Histogram,
    Logger,
    Meter,
    Span,
    Tracer,
)

def _strict_config():
    from observability.settings import _ObservabilityConfig

    return _ObservabilityConfig(
        service_name="test-service",
        log_level="INFO",
        strict_telemetry_errors=True,
    )


def _non_strict_config():
    from observability.settings import _ObservabilityConfig

    return _ObservabilityConfig(
        service_name="test-service",
        log_level="INFO",
        strict_telemetry_errors=False,
    )


def _task_started_envelope(*, task_id: str | None):
    from observability.types import LogEnvelope

    return LogEnvelope(
        event="task_started",
        level="INFO",
        timestamp=datetime.now(UTC),
        message="task started",
        service_name="test-service",
        task_id=task_id,
    )


def _log_envelope(**fields):
    from observability.types import LogEnvelope

    defaults = {
        "event": "general_event",
        "level": "INFO",
        "timestamp": datetime.now(UTC),
        "message": "test message",
        "service_name": "test-service",
    }
    defaults.update(fields)
    return LogEnvelope(**defaults)


def _metric_descriptor(*, metric_type: str):
    from observability.types import MetricDescriptor

    return MetricDescriptor(
        logical_name=f"test.{metric_type}",
        metric_type=metric_type,
        description="test",
        allowed_label_keys=frozenset({"provider", "status"}),
    )


@pytest.mark.ct_obs("CT-OBS-003")
def test_strict_mode_noop_logger_raises_on_missing_task_id() -> None:
    """CT-OBS-003 case: NoOp logger raises InvalidLogEnvelopeError when strict=True."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_strict_config(), pipelines=default_validation_pipelines())

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(_task_started_envelope(task_id=None))


def test_non_strict_noop_logger_skips_validation_for_valid_telemetry() -> None:
    """LLD §11: strict=False yields zero-cost no-op for valid telemetry (no I/O)."""
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    logger.emit(_task_started_envelope(task_id=None))


def test_strict_mode_noop_counter_runs_cardinality_guard() -> None:
    """LLD §11: strict meter instruments run CardinalityGuard on emit."""
    from observability.errors import HighCardinalityLabelError
    from observability.noop import NoOpMeter
    from observability.types import MetricDescriptor

    meter = NoOpMeter(config=_strict_config())
    descriptor = MetricDescriptor(
        logical_name="test.counter",
        metric_type="counter",
        description="test",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    counter = meter.register_counter(descriptor)

    with pytest.raises(HighCardinalityLabelError):
        counter.add(1.0, labels={"workflow_id": "wf-123"})


@pytest.mark.ct_obs("CT-OBS-004")
def test_strict_mode_noop_logger_raises_on_missing_task_attempt() -> None:
    """CT-OBS-004: NoOp logger raises InvalidLogEnvelopeError when task_attempt missing."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_strict_config(), pipelines=default_validation_pipelines())

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(
            _log_envelope(
                event="task_retried",
                task_id="task-1",
                task_attempt=None,
            )
        )


def test_non_strict_noop_logger_skips_validation_for_missing_task_attempt() -> None:
    """LLD §11: strict=False yields zero-cost no-op for invalid task_retried envelope."""
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    logger.emit(
        _log_envelope(
            event="task_retried",
            task_id="task-1",
            task_attempt=None,
        )
    )


@pytest.mark.ct_obs("CT-OBS-005")
def test_strict_mode_noop_logger_raises_on_error_missing_fields() -> None:
    """CT-OBS-005: NoOp logger raises when ERROR envelope lacks error_class/retryable."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_strict_config(), pipelines=default_validation_pipelines())

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(
            _log_envelope(
                event="task_failed",
                level="ERROR",
                error_class=None,
                retryable=None,
            )
        )


def test_non_strict_noop_logger_skips_validation_for_error_missing_fields() -> None:
    """LLD §11: strict=False yields zero-cost no-op for invalid ERROR envelope."""
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    logger.emit(
        _log_envelope(
            event="task_failed",
            level="ERROR",
            error_class=None,
            retryable=None,
        )
    )


@pytest.mark.ct_obs("CT-OBS-006")
def test_strict_mode_noop_logger_raises_on_unredactable_secret() -> None:
    """CT-OBS-006: NoOp logger raises RedactionRequiredError for entirely secret message."""
    from observability.errors import RedactionRequiredError
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_strict_config(), pipelines=default_validation_pipelines())

    with pytest.raises(RedactionRequiredError):
        logger.emit(
            _log_envelope(
                event="general_event",
                message="sk-abcdefghijklmnopqrstuvwxyz1234567890",
            )
        )


def test_non_strict_noop_logger_skips_validation_for_unredactable_secret() -> None:
    """LLD §11: strict=False yields zero-cost no-op for unredactable secret message."""
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    logger.emit(
        _log_envelope(
            event="general_event",
            message="sk-abcdefghijklmnopqrstuvwxyz1234567890",
        )
    )


@pytest.mark.ct_obs("CT-OBS-007")
def test_strict_mode_noop_logger_raises_on_forbidden_prompt_attribute() -> None:
    """CT-OBS-007: NoOp logger raises when prompt appears in envelope attributes."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_strict_config(), pipelines=default_validation_pipelines())

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(_log_envelope(attributes={"prompt": "user prompt text"}))


def test_non_strict_noop_logger_skips_validation_for_forbidden_prompt_attribute() -> None:
    """LLD §11: strict=False yields zero-cost no-op for forbidden prompt attribute."""
    from observability.noop import NoOpLogger
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    logger.emit(_log_envelope(attributes={"prompt": "user prompt text"}))


def test_strict_mode_noop_histogram_runs_cardinality_guard() -> None:
    """LLD §11: strict NoOp histogram runs CardinalityGuard on record."""
    from observability.errors import HighCardinalityLabelError
    from observability.noop import NoOpMeter

    meter = NoOpMeter(config=_strict_config())
    histogram = meter.register_histogram(_metric_descriptor(metric_type="histogram"))

    with pytest.raises(HighCardinalityLabelError):
        histogram.record(1.0, labels={"workflow_id": "wf-123"})


def test_non_strict_noop_histogram_skips_cardinality_guard() -> None:
    """LLD §11: non-strict NoOp histogram is zero-cost for forbidden labels."""
    from observability.noop import NoOpMeter

    meter = NoOpMeter(config=_non_strict_config())
    histogram = meter.register_histogram(_metric_descriptor(metric_type="histogram"))
    histogram.record(1.0, labels={"workflow_id": "wf-123"})


def test_strict_mode_noop_gauge_runs_cardinality_guard() -> None:
    """LLD §11: strict NoOp gauge runs CardinalityGuard on set."""
    from observability.errors import HighCardinalityLabelError
    from observability.noop import NoOpMeter

    meter = NoOpMeter(config=_strict_config())
    gauge = meter.register_gauge(_metric_descriptor(metric_type="gauge"))

    with pytest.raises(HighCardinalityLabelError):
        gauge.set(1.0, labels={"workflow_id": "wf-123"})


def test_non_strict_noop_gauge_skips_cardinality_guard() -> None:
    """LLD §11: non-strict NoOp gauge is zero-cost for forbidden labels."""
    from observability.noop import NoOpMeter

    meter = NoOpMeter(config=_non_strict_config())
    gauge = meter.register_gauge(_metric_descriptor(metric_type="gauge"))
    gauge.set(1.0, labels={"workflow_id": "wf-123"})


def test_noop_correlation_extract_empty_carrier_raises() -> None:
    """NoOp correlation extract raises InvalidTraceContextError on empty carrier."""
    from observability.errors import InvalidTraceContextError
    from observability.noop import NoOpCorrelationContext

    correlation = NoOpCorrelationContext()

    with pytest.raises(InvalidTraceContextError):
        correlation.extract({})


def test_noop_correlation_extract_invalid_traceparent_raises() -> None:
    """NoOp correlation extract raises InvalidTraceContextError on malformed traceparent."""
    from observability.errors import InvalidTraceContextError
    from observability.noop import NoOpCorrelationContext

    correlation = NoOpCorrelationContext()

    with pytest.raises(InvalidTraceContextError):
        correlation.extract({"traceparent": "not-a-valid-traceparent"})


def test_noop_correlation_bind_is_no_op_scope() -> None:
    """NoOp correlation bind returns nullcontext without mutating properties."""
    from observability.noop import NoOpCorrelationContext

    correlation = NoOpCorrelationContext()

    assert correlation.workflow_id is None
    assert correlation.task_id is None
    assert correlation.task_attempt is None

    with correlation.bind(workflow_id="wf-1", task_id="task-1", task_attempt=2):
        assert correlation.workflow_id is None
        assert correlation.task_id is None
        assert correlation.task_attempt is None

    assert correlation.workflow_id is None
    assert correlation.task_id is None
    assert correlation.task_attempt is None


def test_strict_mode_noop_tracer_start_span_forbidden_attribute_raises() -> None:
    """Strict NoOp tracer validates forbidden attributes at start_span."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpTracer

    tracer = NoOpTracer(config=_strict_config())

    with pytest.raises(InvalidLogEnvelopeError):
        tracer.start_span("provider_call", attributes={"response": "secret"})


def test_non_strict_noop_tracer_start_span_skips_validation() -> None:
    """Non-strict NoOp tracer returns context manager without validation."""
    from observability.noop import NoOpTracer

    tracer = NoOpTracer(config=_non_strict_config())

    with tracer.start_span("noop", attributes={"response": "secret"}) as span:
        assert span is not None


def test_strict_mode_noop_span_set_attribute_forbidden_key_raises() -> None:
    """Strict NoOp span validates forbidden keys on set_attribute."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.noop import NoOpTracer

    tracer = NoOpTracer(config=_strict_config())

    with tracer.start_span("provider_call", attributes={"provider": "openai"}) as span:
        with pytest.raises(InvalidLogEnvelopeError):
            span.set_attribute("prompt", "secret content")


def test_noop_types_satisfy_public_protocols() -> None:
    """All NoOp types must satisfy frozen public protocols."""
    from observability.noop import (
        NoOpCorrelationContext,
        NoOpCounter,
        NoOpGauge,
        NoOpHistogram,
        NoOpLogger,
        NoOpMeter,
        NoOpSpan,
        NoOpTracer,
    )
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    meter = NoOpMeter(config=_non_strict_config())
    tracer = NoOpTracer(config=_non_strict_config())
    correlation = NoOpCorrelationContext()

    assert isinstance(logger, Logger)
    assert isinstance(meter, Meter)
    assert isinstance(tracer, Tracer)
    assert isinstance(correlation, CorrelationContext)

    from observability.types import MetricDescriptor

    counter = meter.register_counter(
        MetricDescriptor(
            logical_name="noop.counter",
            metric_type="counter",
            description="noop",
            allowed_label_keys=frozenset({"status"}),
        )
    )
    assert isinstance(counter, Counter)

    histogram = meter.register_histogram(
        MetricDescriptor(
            logical_name="noop.histogram",
            metric_type="histogram",
            description="noop",
            allowed_label_keys=frozenset({"status"}),
        )
    )
    assert isinstance(histogram, Histogram)

    gauge = meter.register_gauge(
        MetricDescriptor(
            logical_name="noop.gauge",
            metric_type="gauge",
            description="noop",
            allowed_label_keys=frozenset({"status"}),
        )
    )
    assert isinstance(gauge, Gauge)

    with tracer.start_span("noop.span") as span:
        assert isinstance(span, Span)
        assert isinstance(span, NoOpSpan)


@pytest.mark.ct_obs("CT-OBS-018")
def test_noop_implementations_callable_without_external_backends() -> None:
    """CT-OBS-018 partial: NoOp path callable without credentials or network."""
    from observability.noop import NoOpLogger, NoOpMeter, NoOpTracer
    from observability.validation import default_validation_pipelines

    logger = NoOpLogger(config=_non_strict_config(), pipelines=default_validation_pipelines())
    meter = NoOpMeter(config=_non_strict_config())
    tracer = NoOpTracer(config=_non_strict_config())

    from observability.types import MetricDescriptor

    logger.info("noop_event", "noop message", status="ok")
    meter.register_counter(
        MetricDescriptor(
            logical_name="noop.counter",
            metric_type="counter",
            description="noop",
            allowed_label_keys=frozenset({"status"}),
        )
    )
    with tracer.start_span("noop"):
        pass
