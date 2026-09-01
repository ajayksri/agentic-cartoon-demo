"""Recording logger fake for contract tests."""

from __future__ import annotations

from observability.correlation import CorrelationContextImpl
from observability.fakes import InMemoryLogger
from observability.settings import _ObservabilityConfig
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def create_recording_logger() -> InMemoryLogger:
    """Construct InMemoryLogger with required observability dependencies."""
    from observability.fakes import RecordingTracer

    config = _ObservabilityConfig(service_name="cartoon-demo-cli", log_level="DEBUG")
    correlation = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())
    tracer = RecordingTracer(config=config, correlation=correlation)
    return InMemoryLogger(config=config, correlation=correlation, tracer=tracer)


RecordingLogger = create_recording_logger
