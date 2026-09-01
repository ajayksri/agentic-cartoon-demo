"""In-memory test doubles sharing production validation pipelines (LLD §13)."""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from observability.cardinality import CardinalityGuard
from observability.correlation import CorrelationContextImpl
from observability.metric_registry import MetricRegistry
from observability.protocols import CorrelationContext, Tracer
from observability.settings import _ObservabilityConfig
from observability.tracer_impl import (
    _run_add_event_pipeline,
    _run_set_attribute_pipeline,
    _run_start_span_pipeline,
)
from observability.types import LogEnvelope, LogLevel, MetricDescriptor, SpanStatus, TraceContext
from observability.validation import (
    ValidationPipelines,
    _json_default,
    default_validation_pipelines,
    envelope_to_json_dict,
)

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


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def _new_span_id() -> str:
    return secrets.token_hex(8)


@dataclass
class RecordedSpan:
    name: str
    attributes: dict[str, object]
    events: list[tuple[str, dict[str, object]]]
    status: SpanStatus
    children: list[RecordedSpan] = field(default_factory=list)


class InMemoryLogger:
    """Implements Logger; stores serialized JSON strings in .records."""

    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: CorrelationContext,
        tracer: Tracer,
        pipelines: ValidationPipelines | None = None,
    ) -> None:
        self._config = config
        self._correlation = correlation
        self._tracer = tracer
        self._pipelines = pipelines or default_validation_pipelines()
        self.records: list[str] = []

    def emit(self, envelope: LogEnvelope) -> None:
        merged = self._pipelines.run_log_validation_pipeline(
            envelope,
            correlation=self._correlation,
            tracer=self._tracer,
            min_level=self._config.log_level,
        )
        if merged is None:
            return

        self._pipelines.validate_bounded_attributes(merged.attributes)
        redacted = self._pipelines.redact_log_envelope(merged)

        payload = json.dumps(
            envelope_to_json_dict(redacted),
            default=_json_default,
            separators=(",", ":"),
        )
        self.records.append(payload)

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


class _CapturingCounter:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        guard: CardinalityGuard,
        meter: CapturingMeter,
    ) -> None:
        self._descriptor = descriptor
        self._guard = guard
        self._meter = meter

    def add(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        self._meter.emissions.append(
            (self._descriptor.logical_name, "add", value, dict(validated))
        )


class _CapturingHistogram:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        guard: CardinalityGuard,
        meter: CapturingMeter,
    ) -> None:
        self._descriptor = descriptor
        self._guard = guard
        self._meter = meter

    def record(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        self._meter.emissions.append(
            (self._descriptor.logical_name, "record", value, dict(validated))
        )


class _CapturingGauge:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        guard: CardinalityGuard,
        meter: CapturingMeter,
    ) -> None:
        self._descriptor = descriptor
        self._guard = guard
        self._meter = meter

    def set(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        self._meter.emissions.append(
            (self._descriptor.logical_name, "set", value, dict(validated))
        )


class CapturingMeter:
    """Implements Meter; stores (logical_name, method, value, labels) in .emissions."""

    def __init__(self, *, config: _ObservabilityConfig) -> None:
        self._config = config
        self._guard = CardinalityGuard()
        self._registry = MetricRegistry()
        self.emissions: list[tuple[str, str, float, dict[str, str]]] = []
        self._counters: dict[str, _CapturingCounter] = {}
        self._histograms: dict[str, _CapturingHistogram] = {}
        self._gauges: dict[str, _CapturingGauge] = {}

    def register_counter(self, descriptor: MetricDescriptor) -> _CapturingCounter:
        registered = self._registry.register(descriptor, lambda name: name)
        cached = self._counters.get(descriptor.logical_name)
        if cached is not None:
            return cached
        wrapper = _CapturingCounter(
            descriptor=registered.descriptor,
            guard=self._guard,
            meter=self,
        )
        self._counters[descriptor.logical_name] = wrapper
        return wrapper

    def register_histogram(self, descriptor: MetricDescriptor) -> _CapturingHistogram:
        registered = self._registry.register(descriptor, lambda name: name)
        cached = self._histograms.get(descriptor.logical_name)
        if cached is not None:
            return cached
        wrapper = _CapturingHistogram(
            descriptor=registered.descriptor,
            guard=self._guard,
            meter=self,
        )
        self._histograms[descriptor.logical_name] = wrapper
        return wrapper

    def register_gauge(self, descriptor: MetricDescriptor) -> _CapturingGauge:
        registered = self._registry.register(descriptor, lambda name: name)
        cached = self._gauges.get(descriptor.logical_name)
        if cached is not None:
            return cached
        wrapper = _CapturingGauge(
            descriptor=registered.descriptor,
            guard=self._guard,
            meter=self,
        )
        self._gauges[descriptor.logical_name] = wrapper
        return wrapper


class _RecordingSpan:
    def __init__(
        self,
        *,
        tracer: RecordingTracer,
        name: str,
        validated_attributes: dict[str, str | int | float | bool],
        parent: _RecordingSpan | None,
        trace_id: str,
        span_id: str,
    ) -> None:
        self._tracer = tracer
        self._name = name
        self._validated_attributes = dict(validated_attributes)
        self._events: list[tuple[str, dict[str, str | int | float | bool]]] = []
        self._status: SpanStatus = "UNSET"
        self._parent = parent
        self._trace_id = trace_id
        self._span_id = span_id
        self._pending_children: list[RecordedSpan] = []

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        validated_key, validated_value = _run_set_attribute_pipeline(key, value)
        self._validated_attributes[validated_key] = validated_value

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        validated = _run_add_event_pipeline(attributes, self._tracer._correlation)
        self._events.append((name, dict(validated)))

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        self.set_attribute("error_class", error_class)
        self.set_attribute("retryable", retryable)
        self._status = "ERROR"

    def end(self, status: SpanStatus = "OK") -> None:
        self._status = status

    def __enter__(self) -> _RecordingSpan:
        self._tracer._span_stack.append(self)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            self._status = "ERROR"
        elif self._status == "UNSET":
            self._status = "OK"

        recorded = RecordedSpan(
            name=self._name,
            attributes=dict(self._validated_attributes),
            events=[(event_name, dict(attrs)) for event_name, attrs in self._events],
            status=self._status,
            children=self._pending_children,
        )

        self._tracer._span_stack.pop()
        if self._parent is None:
            self._tracer.spans.append(recorded)
        else:
            self._parent._pending_children.append(recorded)


class RecordingTracer:
    """Implements Tracer; builds span tree in .spans."""

    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: CorrelationContext,
    ) -> None:
        self._config = config
        self._correlation = correlation
        self.spans: list[RecordedSpan] = []
        self._span_stack: list[_RecordingSpan] = []

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> _RecordingSpan:
        validated = _run_start_span_pipeline(attributes, self._correlation)
        parent = self._span_stack[-1] if self._span_stack else None
        trace_id = parent._trace_id if parent is not None else _new_trace_id()
        span_id = _new_span_id()
        return _RecordingSpan(
            tracer=self,
            name=name,
            validated_attributes=validated,
            parent=parent,
            trace_id=trace_id,
            span_id=span_id,
        )

    def current_trace_context(self) -> TraceContext | None:
        if not self._span_stack:
            return None
        active = self._span_stack[-1]
        return TraceContext(
            trace_id=active._trace_id,
            span_id=active._span_id,
            trace_flags=1,
            is_remote=False,
        )


def create_fake_bindings(
    config: _ObservabilityConfig,
) -> tuple[InMemoryLogger, CapturingMeter, RecordingTracer, CorrelationContextImpl]:
    """Construct wired in-memory fakes for contract/unit tests."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    correlation = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())
    tracer = RecordingTracer(config=config, correlation=correlation)
    logger = InMemoryLogger(config=config, correlation=correlation, tracer=tracer)
    meter = CapturingMeter(config=config)
    return logger, meter, tracer, correlation
