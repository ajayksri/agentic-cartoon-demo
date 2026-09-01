"""Shared contract-test fixtures for api module (API-017, LLD §14)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from .helpers import build_api_dependencies, default_readiness_probes, load_fakes


@pytest.fixture
def api_router_under_test() -> Callable[..., Any]:
    """Build wired API router with injectable FakeWorkflowEngine (LLD §14)."""

    def _factory(
        *,
        engine: Any | None = None,
        readiness_probes: tuple[Any, ...] | None = None,
    ) -> Any:
        from api import create_api_router

        deps = build_api_dependencies(
            engine=engine,
            readiness_probes=readiness_probes,
        )
        return create_api_router(deps=deps)

    return _factory


@pytest.fixture
def api_deps() -> Any:
    """ApiDependencies with default fakes."""
    return build_api_dependencies()


@pytest.fixture
def fake_workflow_engine() -> Any:
    """Fresh FakeWorkflowEngine instance."""
    engine_cls, _probe_cls = load_fakes()
    return engine_cls()


@pytest.fixture
def default_probes() -> tuple[Any, ...]:
    return default_readiness_probes()


@pytest.fixture
def recording_telemetry() -> Any:
    """RecordingApiTelemetry seam for span assertions (LLD §7, allowlisted)."""
    from api.telemetry import RecordingApiTelemetry

    telemetry = RecordingApiTelemetry()
    telemetry.clear()
    return telemetry
