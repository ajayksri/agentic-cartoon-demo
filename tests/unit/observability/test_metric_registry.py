"""Pre-code test mold for OBS-008 — MetricRegistry (CT-OBS-010, CT-OBS-011)."""

from __future__ import annotations

import threading

import pytest


def _make_descriptor(
    logical_name: str = "test.counter",
    metric_type: str = "counter",
    *,
    description: str = "test counter",
    allowed_label_keys: frozenset[str] | None = None,
    unit: str | None = None,
):
    from observability.types import MetricDescriptor

    return MetricDescriptor(
        logical_name=logical_name,
        metric_type=metric_type,  # type: ignore[arg-type]
        description=description,
        allowed_label_keys=allowed_label_keys or frozenset({"provider", "status"}),
        unit=unit,
    )


@pytest.mark.ct_obs("CT-OBS-010")
def test_ct_obs_010_idempotent_registration_returns_same_instrument() -> None:
    """CT-OBS-010: Register same logical_name twice with identical descriptor."""
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    descriptor = _make_descriptor()
    factory_calls: list[str] = []

    def factory(physical_name: str) -> object:
        factory_calls.append(physical_name)
        return object()

    first = registry.register(descriptor, factory)
    second = registry.register(descriptor, factory)

    assert first is second
    assert len(factory_calls) == 1


@pytest.mark.ct_obs("CT-OBS-011")
def test_ct_obs_011_incompatible_metric_type_raises_duplicate_metric_error() -> None:
    """CT-OBS-011: Register same logical_name with different metric_type."""
    from observability.errors import DuplicateMetricError
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    registry.register(_make_descriptor(metric_type="counter"), lambda name: object())

    with pytest.raises(DuplicateMetricError):
        registry.register(_make_descriptor(metric_type="histogram"), lambda name: object())


@pytest.mark.ct_obs("CT-OBS-011")
@pytest.mark.parametrize(
    "conflict_kwargs",
    [
        {"description": "different description"},
        {"unit": "seconds"},
        {"allowed_label_keys": frozenset({"provider", "model"})},
    ],
    ids=["description", "unit", "allowed_label_keys"],
)
def test_ct_obs_011_incompatible_descriptor_fields_raise_duplicate_metric_error(
    conflict_kwargs: dict[str, object],
) -> None:
    """CT-OBS-011: Same logical_name with mismatched non-type fields raises."""
    from observability.errors import DuplicateMetricError
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    factory_calls: list[str] = []

    def factory(physical_name: str) -> object:
        factory_calls.append(physical_name)
        return object()

    base = _make_descriptor(logical_name="compat.counter")
    registry.register(base, factory)

    with pytest.raises(DuplicateMetricError):
        registry.register(_make_descriptor(logical_name="compat.counter", **conflict_kwargs), factory)

    assert len(factory_calls) == 1


def test_registration_rejects_out_of_bounds_label_keys() -> None:
    """LLD §6.3: allowed_label_keys must be subset of BOUNDED_METRIC_LABEL_KEYS."""
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    descriptor = _make_descriptor(allowed_label_keys=frozenset({"provider", "unknown_key"}))

    with pytest.raises(ValueError):
        registry.register(descriptor, lambda name: object())


def test_registration_rejects_forbidden_label_keys() -> None:
    """LLD §6.3: allowed_label_keys must not intersect FORBIDDEN_METRIC_LABEL_KEYS."""
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    descriptor = _make_descriptor(allowed_label_keys=frozenset({"provider", "workflow_id"}))

    with pytest.raises(ValueError):
        registry.register(descriptor, lambda name: object())


def test_metric_name_adapter_applied_to_physical_name() -> None:
    """LLD §6.3: physical_name derived via metric_name_adapter."""
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry(metric_name_adapter=lambda logical: f"prefix.{logical}")
    descriptor = _make_descriptor(logical_name="requests.total")
    registered = registry.register(descriptor, lambda physical: physical)

    assert registered.physical_name == "prefix.requests.total"


def test_get_returns_none_for_unknown_logical_name() -> None:
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    assert registry.get("missing.metric") is None


def test_concurrent_registration_is_thread_safe() -> None:
    """Basic stress: compatible concurrent registration returns same instrument."""
    from observability.metric_registry import MetricRegistry

    registry = MetricRegistry()
    descriptor = _make_descriptor(logical_name="concurrent.counter")
    results: list[object] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(registry.register(descriptor, lambda name: object()))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(item) for item in results}) == 1
