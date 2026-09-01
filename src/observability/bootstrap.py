"""Singleton telemetry bindings and OTel provider bootstrap (LLD §5, §7)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from observability.correlation import CorrelationContextImpl
from observability.logger_impl import LoggerImpl
from observability.metric_registry import MetricRegistry
from observability.meter_impl import MeterImpl
from observability.noop import (
    NoOpCorrelationContext,
    NoOpLogger,
    NoOpMeter,
    NoOpTracer,
)
from observability.protocols import CorrelationContext, Logger, Meter, Tracer
from observability.settings import _ObservabilityConfig, parse_settings
from observability.tracer_impl import TracerImpl
from observability.validation import default_validation_pipelines


@dataclass(frozen=True, slots=True)
class _TelemetryBindings:
    logger: Logger
    meter: Meter
    tracer: Tracer
    correlation_context: CorrelationContext
    config: _ObservabilityConfig


_configure_lock = threading.Lock()
_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None


def _default_config() -> _ObservabilityConfig:
    return _ObservabilityConfig(
        service_name="",
        log_level="INFO",
        strict_telemetry_errors=False,
    )


def _create_noop_bindings(config: _ObservabilityConfig | None = None) -> _TelemetryBindings:
    resolved = config or _default_config()
    pipelines = default_validation_pipelines()
    correlation = NoOpCorrelationContext()
    tracer = NoOpTracer(config=resolved, correlation=correlation)
    logger = NoOpLogger(
        config=resolved,
        pipelines=pipelines,
        correlation=correlation,
        tracer=tracer,
    )
    meter = NoOpMeter(config=resolved)
    return _TelemetryBindings(
        logger=logger,
        meter=meter,
        tracer=tracer,
        correlation_context=correlation,
        config=resolved,
    )


def _build_impl_bindings(config: _ObservabilityConfig) -> _TelemetryBindings:
    import observability

    propagator = TraceContextTextMapPropagator()
    correlation = CorrelationContextImpl(propagator=propagator)
    otel_tracer = trace.get_tracer(__name__, observability.__version__)
    tracer = TracerImpl(config=config, correlation=correlation, otel_tracer=otel_tracer)
    logger = LoggerImpl(config=config, correlation=correlation, tracer=tracer)
    registry = MetricRegistry(metric_name_adapter=config.metric_name_adapter)
    otel_meter = metrics.get_meter(__name__, observability.__version__)
    meter = MeterImpl(config=config, registry=registry, otel_meter=otel_meter)
    return _TelemetryBindings(
        logger=logger,
        meter=meter,
        tracer=tracer,
        correlation_context=correlation,
        config=config,
    )


def _build_otel_providers(config: _ObservabilityConfig) -> tuple[TracerProvider, MeterProvider]:
    resource = Resource.create({"service.name": config.service_name})

    tracer_provider = TracerProvider(resource=resource)
    if config.export_endpoints and config.export_endpoints.traces:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=config.export_endpoints.traces)
            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            console_exporter = ConsoleSpanExporter()
            tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    else:
        console_exporter = ConsoleSpanExporter()
        tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    trace.set_tracer_provider(tracer_provider)

    readers: list[object] = []
    if config.export_endpoints and config.export_endpoints.metrics:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=config.export_endpoints.metrics)
                )
            )
        except ImportError:
            pass

    meter_provider = MeterProvider(resource=resource, metric_readers=readers)  # type: ignore[arg-type]
    metrics.set_meter_provider(meter_provider)

    return tracer_provider, meter_provider


def _shutdown_providers(
    tracer_provider: TracerProvider | None,
    meter_provider: MeterProvider | None,
    *,
    timeout_ms: int = 5000,
) -> None:
    """Flush span processors and shut down meter provider (best-effort)."""
    if tracer_provider is not None:
        try:
            tracer_provider.shutdown()
        except Exception:
            pass
    if meter_provider is not None:
        try:
            meter_provider.shutdown(timeout_millis=timeout_ms)
        except Exception:
            pass


def _unset_otel_global_providers() -> None:
    """Reset OTel API globals so SDK providers can be registered after shutdown."""
    import opentelemetry.metrics._internal as metrics_internal
    import opentelemetry.trace as trace_api
    from opentelemetry.trace import ProxyTracerProvider
    from opentelemetry.util._once import Once

    trace_api._TRACER_PROVIDER = ProxyTracerProvider()
    trace_api._TRACER_PROVIDER_SET_ONCE = Once()
    metrics_internal._METER_PROVIDER = metrics_internal._PROXY_METER_PROVIDER
    metrics_internal._METER_PROVIDER_SET_ONCE = Once()


_bindings: _TelemetryBindings = _create_noop_bindings()


def configure_observability(settings: object) -> None:
    """Bind process-scoped telemetry implementations from opaque runtime settings."""
    global _bindings, _tracer_provider, _meter_provider

    with _configure_lock:
        config = parse_settings(settings)
        _shutdown_providers(_tracer_provider, _meter_provider)
        _unset_otel_global_providers()
        tracer_provider, meter_provider = _build_otel_providers(config)
        _tracer_provider = tracer_provider
        _meter_provider = meter_provider
        _bindings = _build_impl_bindings(config)


def get_logger() -> Logger:
    return _bindings.logger


def get_meter() -> Meter:
    return _bindings.meter


def get_tracer() -> Tracer:
    return _bindings.tracer


def get_correlation_context() -> CorrelationContext:
    return _bindings.correlation_context


def _bootstrap_for_tests(
    *,
    logger: Logger | None = None,
    meter: Meter | None = None,
    tracer: Tracer | None = None,
    correlation_context: CorrelationContext | None = None,
    config: _ObservabilityConfig | object | None = None,
) -> None:
    """Bind test doubles or NoOp defaults without OTel SDK initialization."""
    global _bindings, _tracer_provider, _meter_provider

    with _configure_lock:
        _shutdown_providers(_tracer_provider, _meter_provider)
        _unset_otel_global_providers()
        _tracer_provider = None
        _meter_provider = None

        parsed_config: _ObservabilityConfig | None
        if config is None:
            parsed_config = None
        elif isinstance(config, _ObservabilityConfig):
            parsed_config = config
        else:
            parsed_config = parse_settings(config)

        if parsed_config is not None:
            from observability.fakes import create_fake_bindings

            fake_logger, fake_meter, fake_tracer, fake_correlation = create_fake_bindings(
                parsed_config
            )
            base = _TelemetryBindings(
                logger=fake_logger,
                meter=fake_meter,
                tracer=fake_tracer,
                correlation_context=fake_correlation,
                config=parsed_config,
            )
        else:
            base = _create_noop_bindings(None)

        _bindings = _TelemetryBindings(
            logger=logger if logger is not None else base.logger,
            meter=meter if meter is not None else base.meter,
            tracer=tracer if tracer is not None else base.tracer,
            correlation_context=(
                correlation_context
                if correlation_context is not None
                else base.correlation_context
            ),
            config=parsed_config if parsed_config is not None else base.config,
        )


def _reset_observability_state() -> None:
    """Restore import-time NoOp bindings and tear down OTel providers."""
    global _bindings, _tracer_provider, _meter_provider

    with _configure_lock:
        _shutdown_providers(_tracer_provider, _meter_provider)
        _unset_otel_global_providers()
        _tracer_provider = None
        _meter_provider = None
        _bindings = _create_noop_bindings()
