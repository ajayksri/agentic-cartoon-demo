"""Public API router factory and dependency protocols."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from config.types import AppConfig

if TYPE_CHECKING:
    from observability.types import TraceContext
    from workflow.protocols import WorkflowEngine

from .types import DependencyCheck

T = TypeVar("T")


class MutatingRouteContext(Protocol):
    """Runtime provides active transaction scope around mutating handler invocations (PD-001)."""

    def wrap_mutating(
        self, handler: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        ...


class ReadinessProbe(Protocol):
    """Dependency check injected by runtime (CG-API-010)."""

    name: str

    def check(self) -> DependencyCheck:
        """Return current dependency status without raising."""
        ...


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    """Dependencies supplied to route handlers and router factory."""

    config: AppConfig
    workflow_engine: WorkflowEngine
    readiness_probes: tuple[ReadinessProbe, ...] = ()
    service_name: str = "cartoon-demo-api"


class ApiRouterFactory(Protocol):
    """Creates a mountable API router (FastAPI APIRouter at runtime)."""

    def create_router(self, *, deps: ApiDependencies) -> object:
        """Return router with all routes registered. Type is framework-specific."""
        ...


def create_api_router(
    *,
    deps: ApiDependencies,
    mutating_context: MutatingRouteContext | None = None,
) -> object:
    """Default factory entry point for runtime composition root (PD-001 / LLD-RT-002)."""
    from .router import create_api_router as _create

    return _create(deps=deps, mutating_context=mutating_context)
