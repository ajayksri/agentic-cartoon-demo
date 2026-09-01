"""Canonical contract fixtures for observability (LLD §12.1, OBS-014)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def observability_settings() -> SimpleNamespace:
    """Contract suite settings with strict telemetry validation enabled."""
    return SimpleNamespace(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )


@pytest.fixture
def bootstrap_fakes(observability_settings: SimpleNamespace) -> None:
    """Wire in-memory fakes via internal test hook (LLD §5.3)."""
    from observability.bootstrap import _bootstrap_for_tests

    _bootstrap_for_tests(config=observability_settings)


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """Prevent cross-test binding leakage via bootstrap reset hooks."""
    from observability.bootstrap import _reset_observability_state

    _reset_observability_state()
    yield
    _reset_observability_state()
