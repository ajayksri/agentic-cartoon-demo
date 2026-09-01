"""Public observability error types (OBS-E001–OBS-E006)."""

from __future__ import annotations


class TelemetryNotInitializedError(RuntimeError):
    """Raised when accessors are called before configure_observability (OBS-E001)."""


class InvalidLogEnvelopeError(ValueError):
    """Structured telemetry payload validation failed at instrumentation boundary (OBS-E002)."""


class HighCardinalityLabelError(ValueError):
    """Metric label key or value violates cardinality rules (OBS-E003)."""


class RedactionRequiredError(ValueError):
    """Unredactable secret pattern detected (OBS-E004)."""


class InvalidTraceContextError(ValueError):
    """Malformed carrier or traceparent (OBS-E005)."""


class DuplicateMetricError(ValueError):
    """Incompatible metric re-registration (OBS-E006)."""
