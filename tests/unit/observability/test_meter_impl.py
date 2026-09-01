"""Unit tests for OBS-009 — MeterImpl and instrument wrappers."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from observability.types import MetricDescriptor


def _make_descriptor(
    logical_name: str = "test.counter",
    metric_type: str = "counter",
    *,
    description: str = "test counter",
    allowed_label_keys: frozenset[str] | None = None,
    unit: str | None = None,
) -> MetricDescriptor:
    return MetricDescriptor(
        logical_name=logical_name,
        metric_type=metric_type,  # type: ignore[arg-type]
        description=description,
        allowed_label_keys=allowed_label_keys or frozenset({"provider", "status"}),
        unit=unit,
    )


def _build_meter(*, strict: bool = True):
    from observability.metric_registry import MetricRegistry
    from observability.meter_impl import MeterImpl
    from observability.settings import _ObservabilityConfig

    config = _ObservabilityConfig(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=strict,
    )
    registry = MetricRegistry()
    otel_meter = MagicMock()
    otel_meter.create_counter.return_value = MagicMock()
    otel_meter.create_histogram.return_value = MagicMock()
    otel_meter.create_up_down_counter.return_value = MagicMock()
    meter = MeterImpl(config=config, registry=registry, otel_meter=otel_meter)
    return meter, otel_meter, registry


@pytest.mark.ct_obs("CT-OBS-009")
def test_ct_obs_009_register_and_emit_with_allowed_labels() -> None:
    """CT-OBS-009: Register counter and emit with allowed label keys."""
    meter, otel_meter, _registry = _build_meter()
    descriptor = _make_descriptor(logical_name="provider.calls")

    counter = meter.register_counter(descriptor)
    counter.add(1.0, labels={"provider": "openai", "status": "ok"})

    otel_meter.create_counter.assert_called_once()
    otel_counter = otel_meter.create_counter.return_value
    otel_counter.add.assert_called_once_with(
        1.0,
        attributes={"provider": "openai", "status": "ok"},
    )


@pytest.mark.ct_obs("CT-OBS-008")
def test_ct_obs_008_workflow_id_label_raises_high_cardinality_error() -> None:
    """CT-OBS-008: Emit with workflow_id label raises HighCardinalityLabelError."""
    from observability.errors import HighCardinalityLabelError

    meter, otel_meter, _registry = _build_meter()
    counter = meter.register_counter(_make_descriptor(logical_name="tasks.processed"))

    with pytest.raises(HighCardinalityLabelError):
        counter.add(1.0, labels={"workflow_id": "wf-123"})

    otel_meter.create_counter.return_value.add.assert_not_called()


def test_cardinality_error_raises_when_strict_telemetry_errors_false() -> None:
    """Validation/cardinality errors always raise regardless of strict_telemetry_errors."""
    from observability.errors import HighCardinalityLabelError

    meter, otel_meter, _registry = _build_meter(strict=False)
    counter = meter.register_counter(_make_descriptor())

    with pytest.raises(HighCardinalityLabelError):
        counter.add(1.0, labels={"workflow_id": "wf-123"})

    otel_meter.create_counter.return_value.add.assert_not_called()


def test_histogram_cardinality_error_raises_when_strict_telemetry_errors_false() -> None:
    """Validation/cardinality errors always raise for histogram regardless of strict."""
    from observability.errors import HighCardinalityLabelError

    meter, otel_meter, _registry = _build_meter(strict=False)
    histogram = meter.register_histogram(
        _make_descriptor(logical_name="request.duration", metric_type="histogram")
    )

    with pytest.raises(HighCardinalityLabelError):
        histogram.record(1.0, labels={"workflow_id": "wf-123"})

    otel_meter.create_histogram.return_value.record.assert_not_called()


def test_gauge_cardinality_error_raises_when_strict_telemetry_errors_false() -> None:
    """Validation/cardinality errors always raise for gauge regardless of strict."""
    from observability.errors import HighCardinalityLabelError

    meter, otel_meter, _registry = _build_meter(strict=False)
    gauge = meter.register_gauge(_make_descriptor(logical_name="active.tasks", metric_type="gauge"))

    with pytest.raises(HighCardinalityLabelError):
        gauge.set(1.0, labels={"workflow_id": "wf-123"})

    otel_meter.create_up_down_counter.return_value.add.assert_not_called()


@pytest.mark.ct_obs("CT-OBS-010")
def test_ct_obs_010_compatible_reregistration_returns_same_instrument() -> None:
    """CT-OBS-010: Identical descriptor re-registration returns same wrapper handle."""
    meter, otel_meter, _registry = _build_meter()
    descriptor = _make_descriptor(logical_name="test.counter")

    first = meter.register_counter(descriptor)
    second = meter.register_counter(descriptor)

    assert first is second
    otel_meter.create_counter.assert_called_once()


@pytest.mark.ct_obs("CT-OBS-011")
def test_ct_obs_011_incompatible_reregistration_raises_duplicate_metric_error() -> None:
    """CT-OBS-011: Conflicting metric_type raises DuplicateMetricError."""
    from observability.errors import DuplicateMetricError

    meter, _otel_meter, _registry = _build_meter()
    meter.register_counter(_make_descriptor(logical_name="test.metric", metric_type="counter"))

    with pytest.raises(DuplicateMetricError):
        meter.register_counter(
            _make_descriptor(logical_name="test.metric", metric_type="histogram")
        )


def test_histogram_record_delegates_to_otel() -> None:
    meter, otel_meter, _registry = _build_meter()
    descriptor = _make_descriptor(
        logical_name="request.duration",
        metric_type="histogram",
        unit="ms",
    )

    histogram = meter.register_histogram(descriptor)
    histogram.record(42.5, labels={"provider": "openai", "status": "ok"})

    otel_meter.create_histogram.assert_called_once_with(
        "request.duration",
        unit="ms",
        description="test counter",
    )
    otel_histogram = otel_meter.create_histogram.return_value
    otel_histogram.record.assert_called_once_with(
        42.5,
        attributes={"provider": "openai", "status": "ok"},
    )


def test_gauge_set_applies_up_down_counter_delta_per_label_set() -> None:
    """Gauge V1: set maps to UpDownCounter delta with per-label-set last-value tracking."""
    meter, otel_meter, _registry = _build_meter()
    descriptor = _make_descriptor(
        logical_name="active.tasks",
        metric_type="gauge",
    )

    gauge = meter.register_gauge(descriptor)
    otel_up_down = otel_meter.create_up_down_counter.return_value
    labels = {"provider": "openai", "status": "ok"}

    gauge.set(5.0, labels=labels)
    gauge.set(8.0, labels=labels)
    gauge.set(3.0, labels=labels)

    assert otel_up_down.add.call_count == 3
    otel_up_down.add.assert_any_call(5.0, attributes=labels)
    otel_up_down.add.assert_any_call(3.0, attributes=labels)
    otel_up_down.add.assert_any_call(-5.0, attributes=labels)


def test_gauge_set_tracks_label_sets_independently() -> None:
    meter, otel_meter, _registry = _build_meter()
    gauge = meter.register_gauge(_make_descriptor(logical_name="queue.depth", metric_type="gauge"))
    otel_up_down = otel_meter.create_up_down_counter.return_value

    gauge.set(10.0, labels={"provider": "openai", "status": "ok"})
    gauge.set(20.0, labels={"provider": "anthropic", "status": "ok"})

    otel_up_down.add.assert_any_call(10.0, attributes={"provider": "openai", "status": "ok"})
    otel_up_down.add.assert_any_call(20.0, attributes={"provider": "anthropic", "status": "ok"})


def test_concurrent_registration_returns_same_wrapper() -> None:
    """Compatible concurrent registration returns identical wrapper instance."""
    meter, _otel_meter, _registry = _build_meter()
    descriptor = _make_descriptor(logical_name="concurrent.counter")
    results: list[object] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(meter.register_counter(descriptor))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(item) for item in results}) == 1


def test_gauge_set_concurrent_same_labels_produces_correct_delta_sum() -> None:
    """Concurrent gauge sets on identical labels telescope to final last-value."""
    meter, otel_meter, _registry = _build_meter()
    gauge = meter.register_gauge(
        _make_descriptor(logical_name="concurrent.gauge", metric_type="gauge")
    )
    otel_up_down = otel_meter.create_up_down_counter.return_value
    labels = {"provider": "openai", "status": "ok"}
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    barrier = threading.Barrier(len(values))

    def worker(value: float) -> None:
        barrier.wait()
        gauge.set(value, labels=labels)

    threads = [threading.Thread(target=worker, args=(value,)) for value in values]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    total_delta = sum(call.args[0] for call in otel_up_down.add.call_args_list)
    otel_up_down.reset_mock()
    gauge.set(100.0, labels=labels)
    assert otel_up_down.add.call_args.args[0] == 100.0 - total_delta


def test_meter_impl_satisfies_meter_protocol() -> None:
    from observability.protocols import Counter, Gauge, Histogram, Meter

    meter, _otel_meter, _registry = _build_meter()

    assert isinstance(meter, Meter)
    assert isinstance(
        meter.register_counter(_make_descriptor(logical_name="proto.counter")),
        Counter,
    )
    assert isinstance(
        meter.register_histogram(
            _make_descriptor(logical_name="proto.histogram", metric_type="histogram")
        ),
        Histogram,
    )
    assert isinstance(
        meter.register_gauge(
            _make_descriptor(logical_name="proto.gauge", metric_type="gauge")
        ),
        Gauge,
    )
