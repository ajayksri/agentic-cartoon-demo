"""Meter and instrument implementations (LLD §6.2)."""

from __future__ import annotations

import threading
from collections.abc import Mapping

from opentelemetry import metrics

from observability.cardinality import CardinalityGuard
from observability.metric_registry import MetricRegistry
from observability.settings import _ObservabilityConfig
from observability.types import MetricDescriptor


def _label_set_key(labels: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


class CounterImpl:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        otel_counter: metrics.Counter,
        guard: CardinalityGuard,
    ) -> None:
        self._descriptor = descriptor
        self._otel_counter = otel_counter
        self._guard = guard

    def add(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        self._otel_counter.add(value, attributes=dict(validated))


class HistogramImpl:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        otel_histogram: metrics.Histogram,
        guard: CardinalityGuard,
    ) -> None:
        self._descriptor = descriptor
        self._otel_histogram = otel_histogram
        self._guard = guard

    def record(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        self._otel_histogram.record(value, attributes=dict(validated))


class GaugeImpl:
    def __init__(
        self,
        *,
        descriptor: MetricDescriptor,
        otel_up_down_counter: metrics.UpDownCounter,
        guard: CardinalityGuard,
    ) -> None:
        self._descriptor = descriptor
        self._otel_up_down_counter = otel_up_down_counter
        self._guard = guard
        self._lock = threading.Lock()
        self._last_values: dict[tuple[tuple[str, str], ...], float] = {}

    def set(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        validated = self._guard.validate_labels(self._descriptor, dict(labels or {}))
        label_key = _label_set_key(validated)
        with self._lock:
            last_value = self._last_values.get(label_key, 0.0)
            delta = value - last_value
            self._last_values[label_key] = value
            self._otel_up_down_counter.add(delta, attributes=dict(validated))


class MeterImpl:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        registry: MetricRegistry,
        otel_meter: metrics.Meter,
    ) -> None:
        self._config = config
        self._registry = registry
        self._otel_meter = otel_meter
        self._guard = CardinalityGuard()
        self._lock = threading.Lock()
        self._counters: dict[str, CounterImpl] = {}
        self._histograms: dict[str, HistogramImpl] = {}
        self._gauges: dict[str, GaugeImpl] = {}

    def register_counter(self, descriptor: MetricDescriptor) -> CounterImpl:
        registered = self._registry.register(
            descriptor,
            lambda physical_name: self._otel_meter.create_counter(
                physical_name,
                unit=descriptor.unit or "",
                description=descriptor.description,
            ),
        )
        with self._lock:
            cached = self._counters.get(descriptor.logical_name)
            if cached is not None:
                return cached
            wrapper = CounterImpl(
                descriptor=registered.descriptor,
                otel_counter=registered.otel_instrument,  # type: ignore[arg-type]
                guard=self._guard,
            )
            self._counters[descriptor.logical_name] = wrapper
            return wrapper

    def register_histogram(self, descriptor: MetricDescriptor) -> HistogramImpl:
        registered = self._registry.register(
            descriptor,
            lambda physical_name: self._otel_meter.create_histogram(
                physical_name,
                unit=descriptor.unit or "",
                description=descriptor.description,
            ),
        )
        with self._lock:
            cached = self._histograms.get(descriptor.logical_name)
            if cached is not None:
                return cached
            wrapper = HistogramImpl(
                descriptor=registered.descriptor,
                otel_histogram=registered.otel_instrument,  # type: ignore[arg-type]
                guard=self._guard,
            )
            self._histograms[descriptor.logical_name] = wrapper
            return wrapper

    def register_gauge(self, descriptor: MetricDescriptor) -> GaugeImpl:
        registered = self._registry.register(
            descriptor,
            lambda physical_name: self._otel_meter.create_up_down_counter(
                physical_name,
                unit=descriptor.unit or "",
                description=descriptor.description,
            ),
        )
        with self._lock:
            cached = self._gauges.get(descriptor.logical_name)
            if cached is not None:
                return cached
            wrapper = GaugeImpl(
                descriptor=registered.descriptor,
                otel_up_down_counter=registered.otel_instrument,  # type: ignore[arg-type]
                guard=self._guard,
            )
            self._gauges[descriptor.logical_name] = wrapper
            return wrapper
