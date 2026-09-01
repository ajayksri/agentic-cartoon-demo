"""Observability module public surface."""

from __future__ import annotations

from .bootstrap import (
    configure_observability,
    get_correlation_context,
    get_logger,
    get_meter,
    get_tracer,
)
from .errors import (
    DuplicateMetricError,
    HighCardinalityLabelError,
    InvalidLogEnvelopeError,
    InvalidTraceContextError,
    RedactionRequiredError,
    TelemetryNotInitializedError,
)
from .protocols import (
    CorrelationContext,
    Counter,
    Gauge,
    Histogram,
    Logger,
    Meter,
    Span,
    Tracer,
)
from .types import (
    BOUNDED_METRIC_LABEL_KEYS,
    FORBIDDEN_METRIC_LABEL_KEYS,
    LogEnvelope,
    LogLevel,
    MetricDescriptor,
    MetricType,
    SpanStatus,
    TraceContext,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "BOUNDED_METRIC_LABEL_KEYS",
    "FORBIDDEN_METRIC_LABEL_KEYS",
    "CorrelationContext",
    "Counter",
    "DuplicateMetricError",
    "Gauge",
    "HighCardinalityLabelError",
    "Histogram",
    "InvalidLogEnvelopeError",
    "InvalidTraceContextError",
    "LogEnvelope",
    "LogLevel",
    "Logger",
    "MetricDescriptor",
    "MetricType",
    "Meter",
    "RedactionRequiredError",
    "Span",
    "SpanStatus",
    "TelemetryNotInitializedError",
    "TraceContext",
    "Tracer",
    "configure_observability",
    "get_correlation_context",
    "get_logger",
    "get_meter",
    "get_tracer",
]
