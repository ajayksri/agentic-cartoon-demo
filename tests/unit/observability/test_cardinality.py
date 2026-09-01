"""Pre-code test mold for OBS-007 — metric cardinality guard."""

from __future__ import annotations

import pytest

from observability.types import MetricDescriptor


@pytest.mark.ct_obs("CT-OBS-008")
def test_workflow_id_label_rejected() -> None:
    """CT-OBS-008: workflow_id metric label raises HighCardinalityLabelError."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status", "workflow_id"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError):
        guard.validate_labels(descriptor, {"workflow_id": "wf-123"})


def test_valid_labels_pass_when_allowed_by_descriptor() -> None:
    """Valid labels {provider, status} pass when allowed by descriptor."""
    from observability.cardinality import CardinalityGuard

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()
    labels = {"provider": "openai", "status": "ok"}

    result = guard.validate_labels(descriptor, labels)

    assert result == labels


def test_uuid_like_label_value_rejected() -> None:
    """UUID-like label values raise HighCardinalityLabelError."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError, match="UUID-like"):
        guard.validate_labels(
            descriptor,
            {"provider": "550e8400-e29b-41d4-a716-446655440000"},
        )


def test_raw_url_label_value_rejected() -> None:
    """Raw URL label values raise HighCardinalityLabelError."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError, match="raw URL"):
        guard.validate_labels(descriptor, {"status": "https://example.com/path"})


def test_secret_like_label_value_rejected_at_cardinality_guard() -> None:
    """Secret-like label values raise HighCardinalityLabelError from CardinalityGuard."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError, match="secret-like"):
        guard.validate_labels(
            descriptor,
            {"provider": "sk-abcdefghijklmnopqrstuvwxyz1234567890"},
        )


def test_disallowed_label_key_not_in_descriptor_rejected() -> None:
    """Label keys outside descriptor allowed_label_keys raise HighCardinalityLabelError."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError, match="allowed_label_keys"):
        guard.validate_labels(descriptor, {"model": "gpt-4"})


def test_prompt_like_long_label_value_rejected() -> None:
    """Label values longer than 256 characters raise HighCardinalityLabelError."""
    from observability.cardinality import CardinalityGuard
    from observability.errors import HighCardinalityLabelError

    descriptor = MetricDescriptor(
        logical_name="provider_calls_total",
        metric_type="counter",
        description="Provider call count",
        allowed_label_keys=frozenset({"provider", "status"}),
    )
    guard = CardinalityGuard()

    with pytest.raises(HighCardinalityLabelError, match="maximum length"):
        guard.validate_labels(descriptor, {"status": "x" * 257})
