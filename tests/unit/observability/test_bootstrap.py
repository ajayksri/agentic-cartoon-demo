"""Pre-code test mold for OBS-013 — bootstrap, configure, scaffold alignment."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

LLD_PUBLIC_EXPORTS = frozenset(
    {
        "configure_observability",
        "get_logger",
        "get_meter",
        "get_tracer",
        "get_correlation_context",
        "Logger",
        "Meter",
        "Tracer",
        "CorrelationContext",
        "Counter",
        "Histogram",
        "Gauge",
        "Span",
        "LogEnvelope",
        "LogLevel",
        "MetricDescriptor",
        "MetricType",
        "SpanStatus",
        "TraceContext",
        "BOUNDED_METRIC_LABEL_KEYS",
        "FORBIDDEN_METRIC_LABEL_KEYS",
        "TelemetryNotInitializedError",
        "InvalidLogEnvelopeError",
        "HighCardinalityLabelError",
        "RedactionRequiredError",
        "InvalidTraceContextError",
        "DuplicateMetricError",
        "__version__",
    }
)


def test_pre_init_get_logger_does_not_raise() -> None:
    """LLD-ESC-002: Pre-init get_logger returns NoOp without raising OBS-E001."""
    from observability.bootstrap import _reset_observability_state

    import observability

    _reset_observability_state()
    logger = observability.get_logger()
    assert logger is not None


@pytest.mark.ct_obs("CT-OBS-001")
def test_configure_then_get_returns_non_noop_implementations() -> None:
    """CT-OBS-001: After configure_observability, accessors return non-NoOp impls."""
    from observability.bootstrap import _reset_observability_state
    from observability.noop import (
        NoOpCorrelationContext,
        NoOpLogger,
        NoOpMeter,
        NoOpTracer,
    )

    import observability

    _reset_observability_state()
    settings = SimpleNamespace(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=False,
    )
    observability.configure_observability(settings)

    assert not isinstance(observability.get_logger(), NoOpLogger)
    assert not isinstance(observability.get_meter(), NoOpMeter)
    assert not isinstance(observability.get_tracer(), NoOpTracer)
    assert not isinstance(observability.get_correlation_context(), NoOpCorrelationContext)


def test_configure_observability_signature_excludes_injection_kwargs() -> None:
    """LLD-ESC-003: Public configure accepts only opaque settings."""
    import observability

    sig = inspect.signature(observability.configure_observability)
    params = set(sig.parameters)

    assert params == {"settings"}
    assert "logger" not in params
    assert "meter" not in params
    assert "tracer" not in params
    assert "correlation_context" not in params


def test_init_all_contains_full_lld_public_export_set() -> None:
    """LLD §2.3: __all__ lists complete frozen public surface."""
    import observability

    assert LLD_PUBLIC_EXPORTS <= set(observability.__all__)
    for symbol in LLD_PUBLIC_EXPORTS:
        assert hasattr(observability, symbol), f"missing export: {symbol}"


def test_bootstrap_for_tests_and_reset_restore_import_time_state() -> None:
    """Internal hooks restore import-time NoOp bindings."""
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from observability.noop import NoOpLogger

    import observability

    _reset_observability_state()
    pre_init_logger = observability.get_logger()

    settings = SimpleNamespace(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=False,
    )
    observability.configure_observability(settings)
    assert not isinstance(observability.get_logger(), NoOpLogger)

    _reset_observability_state()
    post_reset_logger = observability.get_logger()
    assert isinstance(post_reset_logger, NoOpLogger)
    assert post_reset_logger is pre_init_logger or isinstance(post_reset_logger, NoOpLogger)

    _bootstrap_for_tests()
    assert observability.get_logger() is not None


def test_bootstrap_imports_only_permitted_modules() -> None:
    """MOD-OBS-INV-018: bootstrap.py must not import forbidden cross-module deps."""
    from pathlib import Path

    forbidden_roots = {"workflow", "worker", "agents", "api", "persistence", "runtime", "config"}
    bootstrap_path = (
        Path(__file__).resolve().parents[3] / "src" / "observability" / "bootstrap.py"
    )
    violations: list[str] = []

    for line in bootstrap_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            for root in forbidden_roots:
                if f" {root}." in f" {stripped}" or f"from {root}" in stripped:
                    violations.append(stripped)

    assert violations == []


@pytest.mark.ct_obs("CT-OBS-001")
def test_reconfigure_replaces_otel_providers_and_functional_accessors() -> None:
    """Reconfigure shuts down prior providers and registers fresh OTel globals."""
    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import TracerProvider

    from observability.bootstrap import _reset_observability_state
    from observability.noop import NoOpLogger

    import observability

    _reset_observability_state()
    settings_a = SimpleNamespace(
        service_name="service-a",
        log_level="INFO",
        strict_telemetry_errors=False,
    )
    observability.configure_observability(settings_a)
    tracer_provider_a = trace.get_tracer_provider()
    meter_provider_a = metrics.get_meter_provider()

    settings_b = SimpleNamespace(
        service_name="service-b",
        log_level="DEBUG",
        strict_telemetry_errors=False,
    )
    observability.configure_observability(settings_b)
    tracer_provider_b = trace.get_tracer_provider()
    meter_provider_b = metrics.get_meter_provider()

    assert tracer_provider_b is not tracer_provider_a
    assert meter_provider_b is not meter_provider_a
    assert isinstance(tracer_provider_b, TracerProvider)
    assert isinstance(meter_provider_b, MeterProvider)
    assert tracer_provider_b.resource.attributes.get("service.name") == "service-b"
    assert not isinstance(observability.get_logger(), NoOpLogger)

    otel_meter = metrics.get_meter("reconfigure-probe")
    counter = otel_meter.create_counter("reconfigure_probe_counter")
    counter.add(1)


def test_configure_invalid_settings_raises_value_error() -> None:
    """Invalid opaque settings fail at configure with ValueError."""
    from observability.bootstrap import _reset_observability_state

    import observability

    _reset_observability_state()
    invalid_settings = SimpleNamespace(log_level="INFO")

    with pytest.raises(ValueError, match="service_name"):
        observability.configure_observability(invalid_settings)


def test_configure_with_export_endpoints_uses_otlp_exporters() -> None:
    """export_endpoints exercises OTLP exporter wiring when extra is available."""
    import sys
    from unittest.mock import MagicMock, patch

    from observability.bootstrap import _reset_observability_state

    import observability

    _reset_observability_state()
    settings = SimpleNamespace(
        service_name="otel-test",
        log_level="INFO",
        strict_telemetry_errors=False,
        export_endpoints=SimpleNamespace(traces="localhost:4317", metrics="localhost:4317"),
    )

    mock_span_exporter_cls = MagicMock()
    mock_metric_exporter_cls = MagicMock()
    mock_trace_exporter_mod = MagicMock(OTLPSpanExporter=mock_span_exporter_cls)
    mock_metric_exporter_mod = MagicMock(OTLPMetricExporter=mock_metric_exporter_cls)

    with (
        patch.dict(
            sys.modules,
            {
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": mock_trace_exporter_mod,
                "opentelemetry.exporter.otlp.proto.grpc.metric_exporter": mock_metric_exporter_mod,
            },
        ),
        patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader") as mock_reader,
    ):
        mock_span_exporter_cls.return_value = MagicMock()
        mock_metric_exporter_cls.return_value = MagicMock()
        mock_reader.return_value = MagicMock()

        observability.configure_observability(settings)

        mock_span_exporter_cls.assert_called_once_with(endpoint="localhost:4317")
        mock_metric_exporter_cls.assert_called_once_with(endpoint="localhost:4317")


def test_build_impl_bindings_uses_module_identity_for_otel_instruments() -> None:
    """LLD §7.2: OTel instruments use bootstrap module name and package version."""
    from unittest.mock import MagicMock, patch

    from observability.bootstrap import _build_impl_bindings, _default_config

    import observability

    config = _default_config()
    with (
        patch("opentelemetry.trace.get_tracer") as mock_get_tracer,
        patch("opentelemetry.metrics.get_meter") as mock_get_meter,
    ):
        mock_get_tracer.return_value = MagicMock()
        mock_get_meter.return_value = MagicMock()
        _build_impl_bindings(config)

        mock_get_tracer.assert_called_once_with(
            "observability.bootstrap", observability.__version__
        )
        mock_get_meter.assert_called_once_with(
            "observability.bootstrap", observability.__version__
        )
