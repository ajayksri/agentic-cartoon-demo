"""Shared fixtures for observability unit tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def strict_telemetry_settings() -> SimpleNamespace:
    """Contract-test settings per LLD §12 (CT-OBS-003–008)."""
    return SimpleNamespace(
        service_name="test-service",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
