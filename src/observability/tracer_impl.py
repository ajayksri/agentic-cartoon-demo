"""Tracer and span implementations with deferred OTel span creation (LLD §6.5, §10)."""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import context, trace

from observability.propagation import otel_span_context_to_trace_context
from observability.protocols import CorrelationContext
from observability.redaction import redact_attribute_map
from observability.settings import _ObservabilityConfig
from observability.types import SpanStatus, TraceContext
from observability.validation import (
    check_forbidden_trace_keys,
    enforce_bounded_trace_scalar,
    merge_correlation_attributes,
)

TraceAttributes = dict[str, str | int | float | bool]


def _validate_trace_attribute_map(
    attributes: Mapping[str, str | int | float | bool],
) -> TraceAttributes:
    """Run trace validation pipeline steps 2–4."""
    check_forbidden_trace_keys(attributes)
    redacted = redact_attribute_map(attributes)
    validated: TraceAttributes = {}
    for key, value in redacted.items():
        validated[key] = enforce_bounded_trace_scalar(key, value)
    return validated


def _run_start_span_pipeline(
    attributes: Mapping[str, str | int | float | bool] | None,
    correlation: CorrelationContext,
) -> TraceAttributes:
    """Run trace validation pipeline steps 1–4 for start_span."""
    merged = merge_correlation_attributes(attributes or {}, correlation)
    return _validate_trace_attribute_map(merged)


def _run_add_event_pipeline(
    attributes: Mapping[str, str | int | float | bool] | None,
    correlation: CorrelationContext,
) -> TraceAttributes:
    """Run trace validation pipeline steps 1–4 for add_event."""
    merged = merge_correlation_attributes(attributes or {}, correlation)
    return _validate_trace_attribute_map(merged)


def _run_set_attribute_pipeline(
    key: str,
    value: str | int | float | bool,
) -> tuple[str, str | int | float | bool]:
    """Run trace validation pipeline steps 2–4 for set_attribute."""
    validated = _validate_trace_attribute_map({key: value})
    return next(iter(validated.items()))


class SpanImpl:
    def __init__(
        self,
        *,
        name: str,
        validated_attributes: TraceAttributes,
        parent_context: context.Context,
        otel_tracer: trace.Tracer,
        config: _ObservabilityConfig,
        correlation: CorrelationContext,
    ) -> None:
        self._name = name
        self._validated_attributes = validated_attributes
        self._parent_context = parent_context
        self._otel_tracer = otel_tracer
        self._config = config
        self._correlation = correlation
        self._otel_span: trace.Span | None = None
        self._attach_token: object | None = None
        self._events: list[tuple[str, TraceAttributes]] = []

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        validated_key, validated_value = _run_set_attribute_pipeline(key, value)
        if self._otel_span is not None:
            self._otel_span.set_attribute(validated_key, validated_value)

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        validated = _run_add_event_pipeline(attributes, self._correlation)
        self._events.append((name, validated))
        if self._otel_span is not None:
            self._otel_span.add_event(name, attributes=validated)

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        self.set_attribute("error_class", error_class)
        self.set_attribute("retryable", retryable)
        if self._otel_span is not None:
            self._otel_span.set_status(trace.Status(trace.StatusCode.ERROR))

    def end(self, status: SpanStatus = "OK") -> None:
        if self._otel_span is None:
            return
        if status == "ERROR":
            self._otel_span.set_status(trace.Status(trace.StatusCode.ERROR))
        elif status == "OK":
            self._otel_span.set_status(trace.Status(trace.StatusCode.OK))
        self._otel_span.end()
        self._otel_span = None

    def __enter__(self) -> SpanImpl:
        self._otel_span = self._otel_tracer.start_span(
            self._name,
            context=self._parent_context,
            attributes=self._validated_attributes,
        )
        otel_ctx = trace.set_span_in_context(self._otel_span)
        self._attach_token = context.attach(otel_ctx)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._otel_span is not None:
            if exc_type is not None:
                self._otel_span.set_status(trace.Status(trace.StatusCode.ERROR))
            self._otel_span.end()
            self._otel_span = None
        if self._attach_token is not None:
            context.detach(self._attach_token)
            self._attach_token = None


class TracerImpl:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: CorrelationContext,
        otel_tracer: trace.Tracer,
    ) -> None:
        self._config = config
        self._correlation = correlation
        self._otel_tracer = otel_tracer

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> SpanImpl:
        validated = _run_start_span_pipeline(attributes, self._correlation)
        parent_context = context.get_current()
        return SpanImpl(
            name=name,
            validated_attributes=validated,
            parent_context=parent_context,
            otel_tracer=self._otel_tracer,
            config=self._config,
            correlation=self._correlation,
        )

    def current_trace_context(self) -> TraceContext | None:
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if not span_context.is_valid:
            return None
        return otel_span_context_to_trace_context(span_context)
