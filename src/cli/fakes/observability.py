"""Observability fakes for CLI tests."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Iterator

from observability.types import MetricDescriptor, SpanStatus, TraceContext


class RecordingSpan:
  def __init__(self, name: str) -> None:
      self.name = name
      self.attributes: dict[str, object] = {}
      self.exceptions: list[tuple[str, bool]] = []
      self.status: SpanStatus | None = None

  def set_attribute(self, key: str, value: str | int | float | bool) -> None:
      self.attributes[key] = value

  def add_event(
      self,
      name: str,
      *,
      attributes: Mapping[str, str | int | float | bool] | None = None,
  ) -> None:
      _ = (name, attributes)

  def record_exception(self, error_class: str, *, retryable: bool) -> None:
      self.exceptions.append((error_class, retryable))

  def end(self, status: SpanStatus = "OK") -> None:
      self.status = status

  def __enter__(self) -> RecordingSpan:
      return self

  def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
      return None


class RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    def clear(self) -> None:
        self.spans.clear()

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> RecordingSpan:
        _ = attributes
        span = RecordingSpan(name)
        self.spans.append(span)
        return span

    def current_trace_context(self) -> TraceContext | None:
        return None


class RecordingMeter:
    def __init__(self) -> None:
        self.counters: list[tuple[str, float, dict[str, str] | None]] = []
        self.histograms: list[tuple[str, float, dict[str, str] | None]] = []

    def clear(self) -> None:
        self.counters.clear()
        self.histograms.clear()

    def register_counter(self, descriptor: MetricDescriptor) -> RecordingCounter:
        return RecordingCounter(descriptor.name, self)

    def register_histogram(self, descriptor: MetricDescriptor) -> RecordingHistogram:
        return RecordingHistogram(descriptor.name, self)


class RecordingCounter:
    def __init__(self, name: str, meter: RecordingMeter) -> None:
        self._name = name
        self._meter = meter

    def add(self, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        self._meter.counters.append((self._name, value, dict(labels) if labels else None))


class RecordingHistogram:
    def __init__(self, name: str, meter: RecordingMeter) -> None:
        self._name = name
        self._meter = meter

    def record(self, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self._meter.histograms.append((self._name, value, dict(labels) if labels else None))
