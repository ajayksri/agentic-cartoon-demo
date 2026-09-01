"""Contract test skeleton for CT-OBS-001 through CT-OBS-018 (OBS-014)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


def _log_envelope(**overrides: object):
    from observability.types import LogEnvelope

    defaults = {
        "event": "workflow_created",
        "level": "INFO",
        "timestamp": datetime.now(UTC),
        "message": "contract test",
        "service_name": "test-service",
    }
    defaults.update(overrides)
    return LogEnvelope(**defaults)  # type: ignore[arg-type]


@pytest.mark.ct_obs("CT-OBS-001")
def test_ct_obs_001_process_initialization_returns_non_noop(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-001: configure_observability then get_* returns non-NoOp implementations."""
    from observability.noop import (
        NoOpCorrelationContext,
        NoOpLogger,
        NoOpMeter,
        NoOpTracer,
    )

    import observability

    observability.configure_observability(observability_settings)

    assert not isinstance(observability.get_logger(), NoOpLogger)
    assert not isinstance(observability.get_meter(), NoOpMeter)
    assert not isinstance(observability.get_tracer(), NoOpTracer)
    assert not isinstance(observability.get_correlation_context(), NoOpCorrelationContext)


@pytest.mark.ct_obs("CT-OBS-002")
def test_ct_obs_002_workflow_log_correlation(bootstrap_fakes: None) -> None:
    """CT-OBS-002: workflow_created envelope serializes workflow_id."""
    from observability.fakes import InMemoryLogger

    import observability

    logger = observability.get_logger()
    assert isinstance(logger, InMemoryLogger)

    logger.emit(_log_envelope(event="workflow_created", workflow_id="wf-123"))
    assert any("wf-123" in record for record in logger.records)


@pytest.mark.ct_obs("CT-OBS-003")
def test_ct_obs_003_task_log_correlation_rejection(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-003: task_started without task_id raises InvalidLogEnvelopeError."""
    from observability.errors import InvalidLogEnvelopeError

    import observability

    observability.configure_observability(observability_settings)
    logger = observability.get_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(_log_envelope(event="task_started", task_id=None))


@pytest.mark.ct_obs("CT-OBS-004")
def test_ct_obs_004_retry_attempt_required(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-004: task_retried without task_attempt raises InvalidLogEnvelopeError."""
    from observability.errors import InvalidLogEnvelopeError

    import observability

    observability.configure_observability(observability_settings)
    logger = observability.get_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(_log_envelope(event="task_retried", task_id="task-1", task_attempt=None))


@pytest.mark.ct_obs("CT-OBS-005")
def test_ct_obs_005_error_envelope_fields(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-005: ERROR envelope missing error_class/retryable raises."""
    from observability.errors import InvalidLogEnvelopeError

    import observability

    observability.configure_observability(observability_settings)
    logger = observability.get_logger()

    with pytest.raises(InvalidLogEnvelopeError, match="error_class.*retryable"):
        logger.emit(
            _log_envelope(
                event="general_event",
                level="ERROR",
                error_class=None,
                retryable=None,
            )
        )


@pytest.mark.ct_obs("CT-OBS-006")
def test_ct_obs_006_secret_redaction(bootstrap_fakes: None) -> None:
    """CT-OBS-006: Secret-like attribute redacted or raises RedactionRequiredError."""
    from observability.errors import RedactionRequiredError
    from observability.fakes import InMemoryLogger

    import observability

    logger = observability.get_logger()
    assert isinstance(logger, InMemoryLogger)

    envelope = _log_envelope(
        event="general_event",
        message="prefix sk-abcdefghijklmnopqrstuvwxyz123456 suffix",
    )
    try:
        logger.emit(envelope)
    except RedactionRequiredError:
        pass
    else:
        serialized = "".join(logger.records)
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in serialized


@pytest.mark.ct_obs("CT-OBS-007")
def test_ct_obs_007_prompt_response_exclusion(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-007: prompt/response body fields blocked at log boundary."""
    from observability.errors import InvalidLogEnvelopeError

    import observability

    observability.configure_observability(observability_settings)
    logger = observability.get_logger()

    with pytest.raises(InvalidLogEnvelopeError):
        logger.emit(_log_envelope(attributes={"prompt": "user prompt text"}))


@pytest.mark.ct_obs("CT-OBS-008")
def test_ct_obs_008_high_cardinality_metric_label_rejection(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-008: workflow_id metric label raises HighCardinalityLabelError."""
    from observability.errors import HighCardinalityLabelError
    from observability.types import MetricDescriptor

    import observability

    observability.configure_observability(observability_settings)
    meter = observability.get_meter()
    counter = meter.register_counter(
        MetricDescriptor(
            logical_name="tasks.processed",
            metric_type="counter",
            description="tasks",
            allowed_label_keys=frozenset({"provider", "status"}),
        )
    )

    with pytest.raises(HighCardinalityLabelError):
        counter.add(1.0, labels={"workflow_id": "wf-123"})


@pytest.mark.ct_obs("CT-OBS-009")
def test_ct_obs_009_allowed_metric_labels(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-009: Allowed descriptor label keys emit successfully."""
    from observability.types import MetricDescriptor

    import observability

    observability.configure_observability(observability_settings)
    meter = observability.get_meter()
    counter = meter.register_counter(
        MetricDescriptor(
            logical_name="provider.calls",
            metric_type="counter",
            description="provider calls",
            allowed_label_keys=frozenset({"provider", "status"}),
        )
    )
    counter.add(1.0, labels={"provider": "openai", "status": "ok"})


@pytest.mark.ct_obs("CT-OBS-010")
def test_ct_obs_010_metric_descriptor_idempotency() -> None:
    """CT-OBS-010: Identical descriptor re-registration returns same instrument."""
    from observability.metric_registry import MetricRegistry
    from observability.types import MetricDescriptor

    registry = MetricRegistry()
    descriptor = MetricDescriptor(
        logical_name="test.counter",
        metric_type="counter",
        description="test",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    first = registry.register(descriptor, lambda name: object())
    second = registry.register(descriptor, lambda name: object())
    assert first is second


@pytest.mark.ct_obs("CT-OBS-011")
def test_ct_obs_011_incompatible_metric_re_registration() -> None:
    """CT-OBS-011: Conflicting metric_type raises DuplicateMetricError."""
    from observability.errors import DuplicateMetricError
    from observability.metric_registry import MetricRegistry
    from observability.types import MetricDescriptor

    registry = MetricRegistry()
    base = MetricDescriptor(
        logical_name="test.metric",
        metric_type="counter",
        description="test",
        allowed_label_keys=frozenset({"status"}),
    )
    registry.register(base, lambda name: object())
    conflicting = MetricDescriptor(
        logical_name="test.metric",
        metric_type="histogram",
        description="test",
        allowed_label_keys=frozenset({"status"}),
    )
    with pytest.raises(DuplicateMetricError):
        registry.register(conflicting, lambda name: object())


@pytest.mark.ct_obs("CT-OBS-012")
def test_ct_obs_012_trace_context_inject_extract_round_trip(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-012: inject/extract preserves trace_id and span_id."""
    import observability

    observability.configure_observability(observability_settings)
    correlation = observability.get_correlation_context()
    tracer = observability.get_tracer()
    carrier: dict[str, str] = {}
    with tracer.start_span("contract.test"):
        injected = tracer.current_trace_context()
        assert injected is not None
        correlation.inject(carrier)
    extracted = correlation.extract(carrier)
    assert extracted.trace_id == injected.trace_id
    assert extracted.span_id == injected.span_id


@pytest.mark.ct_obs("CT-OBS-013")
def test_ct_obs_013_malformed_trace_carrier(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-013: Invalid traceparent raises InvalidTraceContextError."""
    from observability.errors import InvalidTraceContextError

    import observability

    observability.configure_observability(observability_settings)
    correlation = observability.get_correlation_context()

    with pytest.raises(InvalidTraceContextError):
        correlation.extract({"traceparent": "not-a-valid-traceparent"})


@pytest.mark.ct_obs("CT-OBS-014")
def test_ct_obs_014_retry_visibility_in_tracing(bootstrap_fakes: None) -> None:
    """CT-OBS-014: Distinct retry spans/events recorded, not collapsed."""
    from observability.fakes import RecordingTracer

    import observability

    tracer = observability.get_tracer()
    assert isinstance(tracer, RecordingTracer)

    with tracer.start_span("task.execute") as span:
        span.add_event("retry", attributes={"task_attempt": 1})
    with tracer.start_span("task.execute.retry") as retry_span:
        retry_span.add_event("retry", attributes={"task_attempt": 2})

    assert len(tracer.spans) >= 2
    retry_attempts = [
        attrs["task_attempt"]
        for span in tracer.spans
        for event_name, attrs in span.events
        if event_name == "retry" and "task_attempt" in attrs
    ]
    assert len(retry_attempts) >= 2
    assert len(set(retry_attempts)) >= 2


@pytest.mark.ct_obs("CT-OBS-015")
def test_ct_obs_015_provider_span_attributes(bootstrap_fakes: None) -> None:
    """CT-OBS-015: Provider attrs allowed; prompt/response forbidden."""
    from observability.errors import InvalidLogEnvelopeError
    from observability.fakes import RecordingTracer

    import observability

    tracer = observability.get_tracer()
    assert isinstance(tracer, RecordingTracer)

    with tracer.start_span(
        "provider_call_openai",
        attributes={"provider": "openai", "model": "gpt-4", "status": "ok"},
    ):
        pass

    assert len(tracer.spans) == 1
    recorded = tracer.spans[0]
    assert recorded.attributes["provider"] == "openai"
    assert recorded.attributes["model"] == "gpt-4"
    assert recorded.attributes["status"] == "ok"

    with pytest.raises(InvalidLogEnvelopeError):
        tracer.start_span("provider_call_openai", attributes={"response": "secret"})


@pytest.mark.ct_obs("CT-OBS-016")
def test_ct_obs_016_correlation_context_bind_scope(
    observability_settings: SimpleNamespace,
) -> None:
    """CT-OBS-016: bind scope restores workflow_id outside context."""
    import observability

    observability.configure_observability(observability_settings)
    correlation = observability.get_correlation_context()

    assert correlation.workflow_id is None
    with correlation.bind(workflow_id="wf-1"):
        assert correlation.workflow_id == "wf-1"
    assert correlation.workflow_id is None


def _find_forbidden_observability_imports() -> list[str]:
    """AST scan for forbidden cross-module imports under src/observability."""
    import ast
    from pathlib import Path

    forbidden_roots = {"workflow", "worker", "agents", "api", "persistence"}
    src_root = Path(__file__).resolve().parents[3] / "src" / "observability"
    violations: list[str] = []

    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in forbidden_roots:
                        violations.append(f"{path.relative_to(src_root)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                root = node.module.split(".")[0]
                if root in forbidden_roots:
                    violations.append(
                        f"{path.relative_to(src_root)}: from {node.module} import ..."
                    )

    return violations


@pytest.mark.ct_obs("CT-OBS-017")
def test_ct_obs_017_no_forbidden_imports() -> None:
    """CT-OBS-017: src/observability has no forbidden cross-module imports."""
    assert _find_forbidden_observability_imports() == []


@pytest.mark.ct_obs("CT-OBS-018")
def test_ct_obs_018_no_op_test_double_without_credentials(bootstrap_fakes: None) -> None:
    """CT-OBS-018: In-memory/no-op implementations run without external backends."""
    from observability.fakes import CapturingMeter, InMemoryLogger, RecordingTracer

    import observability

    assert isinstance(observability.get_logger(), InMemoryLogger)
    assert isinstance(observability.get_meter(), CapturingMeter)
    assert isinstance(observability.get_tracer(), RecordingTracer)
