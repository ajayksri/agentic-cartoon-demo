"""No-op telemetry implementations for import-time and test defaults (LLD §11)."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime

from observability.cardinality import CardinalityGuard
from observability.errors import InvalidTraceContextError
from observability.propagation import extract_trace_context
from observability.settings import _ObservabilityConfig
from observability.types import LogEnvelope, LogLevel, MetricDescriptor, SpanStatus, TraceContext
from observability.validation import ValidationPipelines, default_validation_pipelines
from observability.validation import (
    check_forbidden_trace_keys,
    enforce_bounded_trace_scalar,
    merge_correlation_attributes,
)
from observability.redaction import redact_attribute_map

_ENVELOPE_FIELD_KEYS = frozenset(
    {
        "workflow_id",
        "task_id",
        "task_attempt",
        "trace_id",
        "span_id",
        "error_class",
        "retryable",
    }
)


def _validate_trace_attribute_map(
    attributes: Mapping[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    check_forbidden_trace_keys(attributes)
    redacted = redact_attribute_map(attributes)
    validated: dict[str, str | int | float | bool] = {}
    for key, value in redacted.items():
        validated[key] = enforce_bounded_trace_scalar(key, value)
    return validated


def _run_start_span_pipeline(
    attributes: Mapping[str, str | int | float | bool] | None,
    correlation: NoOpCorrelationContext,
) -> dict[str, str | int | float | bool]:
    merged = merge_correlation_attributes(attributes or {}, correlation)
    return _validate_trace_attribute_map(merged)


def _run_set_attribute_pipeline(
    key: str,
    value: str | int | float | bool,
) -> tuple[str, str | int | float | bool]:
    validated = _validate_trace_attribute_map({key: value})
    return next(iter(validated.items()))


def _run_add_event_pipeline(
    attributes: Mapping[str, str | int | float | bool] | None,
    correlation: NoOpCorrelationContext,
) -> dict[str, str | int | float | bool]:
    merged = merge_correlation_attributes(attributes or {}, correlation)
    return _validate_trace_attribute_map(merged)


class NoOpLogger:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        pipelines: ValidationPipelines | None = None,
        correlation: NoOpCorrelationContext | None = None,
        tracer: NoOpTracer | None = None,
    ) -> None:
        self._config = config
        self._pipelines = pipelines or default_validation_pipelines()
        self._correlation = correlation or NoOpCorrelationContext()
        self._tracer = tracer or NoOpTracer(config=config, correlation=self._correlation)

    def emit(self, envelope: LogEnvelope) -> None:
        """No I/O. Run full pipeline only when config.strict_telemetry_errors else no-op."""
        if not self._config.strict_telemetry_errors:
            return

        merged = self._pipelines.run_log_validation_pipeline(
            envelope,
            correlation=self._correlation,
            tracer=self._tracer,
            min_level=self._config.log_level,
        )
        if merged is None:
            return

        self._pipelines.validate_bounded_attributes(merged.attributes)
        self._pipelines.redact_log_envelope(merged)

    def debug(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("DEBUG", event, message, **fields))

    def info(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("INFO", event, message, **fields))

    def warning(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("WARNING", event, message, **fields))

    def error(
        self,
        event: str,
        message: str,
        *,
        error_class: str,
        retryable: bool,
        **fields: str | int | float | bool,
    ) -> None:
        self.emit(
            self._build_envelope(
                "ERROR",
                event,
                message,
                error_class=error_class,
                retryable=retryable,
                **fields,
            )
        )

    def _build_envelope(
        self,
        level: LogLevel,
        event: str,
        message: str,
        **fields: str | int | float | bool,
    ) -> LogEnvelope:
        top_level: dict[str, object] = {}
        attributes: dict[str, str | int | float | bool] = {}

        for key, value in fields.items():
            if key in _ENVELOPE_FIELD_KEYS:
                top_level[key] = value
            else:
                attributes[key] = value

        if "workflow_id" not in top_level and self._correlation.workflow_id is not None:
            top_level["workflow_id"] = self._correlation.workflow_id
        if "task_id" not in top_level and self._correlation.task_id is not None:
            top_level["task_id"] = self._correlation.task_id
        if "task_attempt" not in top_level and self._correlation.task_attempt is not None:
            top_level["task_attempt"] = self._correlation.task_attempt

        trace_ctx = self._tracer.current_trace_context()
        if trace_ctx is not None:
            if "trace_id" not in top_level:
                top_level["trace_id"] = trace_ctx.trace_id
            if "span_id" not in top_level:
                top_level["span_id"] = trace_ctx.span_id

        return LogEnvelope(
            event=event,
            level=level,
            timestamp=datetime.now(UTC),
            message=message,
            service_name=self._config.service_name,
            attributes=attributes,
            **top_level,  # type: ignore[arg-type]
        )


class NoOpCounter:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        config: _ObservabilityConfig,
        guard: CardinalityGuard | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._config = config
        self._guard = guard or CardinalityGuard()

    def add(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        del value
        if not self._config.strict_telemetry_errors:
            return
        self._guard.validate_labels(self._descriptor, labels or {})


class NoOpHistogram:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        config: _ObservabilityConfig,
        guard: CardinalityGuard | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._config = config
        self._guard = guard or CardinalityGuard()

    def record(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        del value
        if not self._config.strict_telemetry_errors:
            return
        self._guard.validate_labels(self._descriptor, labels or {})


class NoOpGauge:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        config: _ObservabilityConfig,
        guard: CardinalityGuard | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._config = config
        self._guard = guard or CardinalityGuard()

    def set(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        del value
        if not self._config.strict_telemetry_errors:
            return
        self._guard.validate_labels(self._descriptor, labels or {})


class NoOpMeter:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        guard: CardinalityGuard | None = None,
    ) -> None:
        self._config = config
        self._guard = guard or CardinalityGuard()

    def register_counter(self, descriptor: MetricDescriptor) -> NoOpCounter:
        return NoOpCounter(descriptor=descriptor, config=self._config, guard=self._guard)

    def register_histogram(self, descriptor: MetricDescriptor) -> NoOpHistogram:
        return NoOpHistogram(descriptor=descriptor, config=self._config, guard=self._guard)

    def register_gauge(self, descriptor: MetricDescriptor) -> NoOpGauge:
        return NoOpGauge(descriptor=descriptor, config=self._config, guard=self._guard)


class NoOpSpan:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: NoOpCorrelationContext,
        validated_attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        self._config = config
        self._correlation = correlation
        self._validated_attributes = dict(validated_attributes or {})

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        if self._config.strict_telemetry_errors:
            _run_set_attribute_pipeline(key, value)

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        del name
        if self._config.strict_telemetry_errors:
            _run_add_event_pipeline(attributes, self._correlation)

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        self.set_attribute("error_class", error_class)
        self.set_attribute("retryable", retryable)

    def end(self, status: SpanStatus = "OK") -> None:
        del status

    def __enter__(self) -> NoOpSpan:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        del exc_type, exc_val, exc_tb


class NoOpTracer:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: NoOpCorrelationContext | None = None,
    ) -> None:
        self._config = config
        self._correlation = correlation or NoOpCorrelationContext()

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> NoOpSpan:
        validated: dict[str, str | int | float | bool] | None = None
        if self._config.strict_telemetry_errors:
            validated = _run_start_span_pipeline(attributes, self._correlation)
        return NoOpSpan(
            config=self._config,
            correlation=self._correlation,
            validated_attributes=validated,
        )

    def current_trace_context(self) -> TraceContext | None:
        return None


class NoOpCorrelationContext:
    @property
    def workflow_id(self) -> str | None:
        return None

    @property
    def task_id(self) -> str | None:
        return None

    @property
    def task_attempt(self) -> int | None:
        return None

    def bind(
        self,
        *,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> AbstractContextManager[None]:
        del workflow_id, task_id, task_attempt
        return nullcontext()

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        del carrier

    def extract(self, carrier: Mapping[str, str]) -> TraceContext:
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        try:
            return extract_trace_context(carrier, propagator=TraceContextTextMapPropagator())
        except InvalidTraceContextError:
            raise
        except Exception as exc:
            raise InvalidTraceContextError(
                f"Failed to extract trace context: {exc}"
            ) from exc

    def attach(self, ctx: TraceContext) -> AbstractContextManager[None]:
        del ctx
        return nullcontext()
