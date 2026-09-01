"""API-018 — public mutating_context on create_api_router (PD-001)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import api
from api import create_api_router

from tests.contract.api.helpers import build_api_dependencies


class _RecordingMutatingContext:
    def __init__(self) -> None:
        self.wrap_calls = 0

    def wrap_mutating(
        self, handler: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        self.wrap_calls += 1
        return handler


def test_create_api_router_accepts_optional_mutating_context() -> None:
    mutating = _RecordingMutatingContext()
    deps = build_api_dependencies()
    router = create_api_router(deps=deps, mutating_context=mutating)
    assert router is not None
    assert mutating.wrap_calls == 2


def test_create_api_router_backward_compatible_without_mutating_context() -> None:
    deps = build_api_dependencies()
    router = create_api_router(deps=deps)
    assert router is not None


def test_mutating_route_context_exported() -> None:
    assert "MutatingRouteContext" in api.__all__
    assert hasattr(api, "MutatingRouteContext")
