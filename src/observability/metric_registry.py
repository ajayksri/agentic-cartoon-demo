"""Metric instrument registry (LLD §6.3)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from observability.errors import DuplicateMetricError
from observability.types import (
    BOUNDED_METRIC_LABEL_KEYS,
    FORBIDDEN_METRIC_LABEL_KEYS,
    MetricDescriptor,
)


@dataclass(frozen=True, slots=True)
class RegisteredInstrument:
    descriptor: MetricDescriptor
    physical_name: str
    otel_instrument: object


def _descriptors_compatible(existing: MetricDescriptor, incoming: MetricDescriptor) -> bool:
    return (
        existing.metric_type == incoming.metric_type
        and existing.allowed_label_keys == incoming.allowed_label_keys
        and existing.description == incoming.description
        and existing.unit == incoming.unit
    )


class MetricRegistry:
    """Thread-safe in-process metric instrument table keyed by logical_name."""

    def __init__(self, *, metric_name_adapter: Callable[[str], str] | None = None) -> None:
        self._metric_name_adapter = metric_name_adapter or (lambda logical_name: logical_name)
        self._lock = threading.Lock()
        self._instruments: dict[str, RegisteredInstrument] = {}

    def register(
        self,
        descriptor: MetricDescriptor,
        factory: Callable[[str], object],
    ) -> RegisteredInstrument:
        """Thread-safe; idempotent for compatible descriptor; DuplicateMetricError on conflict."""
        _validate_descriptor_label_keys(descriptor)

        with self._lock:
            existing = self._instruments.get(descriptor.logical_name)
            if existing is not None:
                if not _descriptors_compatible(existing.descriptor, descriptor):
                    raise DuplicateMetricError(
                        f"Incompatible metric re-registration for "
                        f"{descriptor.logical_name!r} (OBS-E006)."
                    )
                return existing

            physical_name = self._metric_name_adapter(descriptor.logical_name)
            otel_instrument = factory(physical_name)
            registered = RegisteredInstrument(
                descriptor=descriptor,
                physical_name=physical_name,
                otel_instrument=otel_instrument,
            )
            self._instruments[descriptor.logical_name] = registered
            return registered

    def get(self, logical_name: str) -> RegisteredInstrument | None:
        with self._lock:
            return self._instruments.get(logical_name)


def _validate_descriptor_label_keys(descriptor: MetricDescriptor) -> None:
    if not descriptor.allowed_label_keys <= BOUNDED_METRIC_LABEL_KEYS:
        out_of_bounds = descriptor.allowed_label_keys - BOUNDED_METRIC_LABEL_KEYS
        key = sorted(out_of_bounds)[0]
        raise ValueError(
            f"Metric descriptor allowed_label_keys contains out-of-bounds key {key!r}"
        )

    forbidden = descriptor.allowed_label_keys & FORBIDDEN_METRIC_LABEL_KEYS
    if forbidden:
        key = sorted(forbidden)[0]
        raise ValueError(
            f"Metric descriptor allowed_label_keys contains forbidden key {key!r}"
        )
