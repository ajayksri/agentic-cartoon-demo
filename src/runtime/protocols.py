"""Public runtime protocol definitions and bootstrap factories."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

from config.types import AppConfig, ConfigSource, TaskType

from .types import (
    BootstrapResult,
    CoordinatorLoopConfig,
    OutboxPublisherConfig,
    ProcessEntryPoint,
    WiredDependencies,
)

if TYPE_CHECKING:
    from failure_injection.protocols import FailureInjectionRegistry
    from observability.protocols import Logger, Meter, Tracer
    from persistence.protocols import OutboxRepo, WorkflowRepo
    from task_queue.protocols import TaskQueue
    from workflow.protocols import WorkflowEngine


class OutboxPublisherLoop(Protocol):
    """Coordinator loop: persistence outbox → task_queue.enqueue (ADR-002)."""

    def run(self) -> None:
        """Block publishing batches until stop() or fatal error."""
        ...

    def stop(self) -> None:
        """Request graceful shutdown after current batch completes."""
        ...


class CompositionRoot(Protocol):
    """Product composition root: load config and wire process-scoped collaborators."""

    @property
    def config(self) -> AppConfig:
        """Validated application configuration loaded at root construction."""
        ...

    def bootstrap(self, entry: ProcessEntryPoint) -> BootstrapResult:
        """Wire dependencies for the given process entry point."""
        ...

    def wired_dependencies(self) -> WiredDependencies:
        """Return snapshot of collaborators after last successful bootstrap."""
        ...


def create_composition_root(
    *,
    source: ConfigSource | None = None,
) -> CompositionRoot:
    """Load config and return a composition root ready for bootstrap()."""
    from .composition import create_composition_root as _create

    return _create(source=source)


def create_outbox_publisher_loop(
    *,
    config: AppConfig,
    publisher_config: OutboxPublisherConfig,
    outbox_repo: OutboxRepo,
    workflow_repo: WorkflowRepo,
    task_queue: TaskQueue,
    workflow_engine: WorkflowEngine,
    failure_injection: FailureInjectionRegistry,
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
    shutdown: threading.Event | None = None,
) -> OutboxPublisherLoop:
    """Factory for the default OutboxPublisherLoop (coordinator wiring)."""
    from .outbox import create_outbox_publisher_loop as _create

    return _create(
        config=config,
        publisher_config=publisher_config,
        outbox_repo=outbox_repo,
        workflow_repo=workflow_repo,
        task_queue=task_queue,
        workflow_engine=workflow_engine,
        failure_injection=failure_injection,
        logger=logger,
        meter=meter,
        tracer=tracer,
        shutdown=shutdown,
    )


def run_api_process(*, source: ConfigSource | None = None) -> None:
    """Bootstrap and run the API process until shutdown."""
    from .runners import run_api_process as _run

    _run(source=source)


def run_coordinator_process(
    *,
    source: ConfigSource | None = None,
    loop_config: CoordinatorLoopConfig | None = None,
) -> None:
    """Bootstrap and run the coordinator process until shutdown."""
    from .runners import run_coordinator_process as _run

    _run(source=source, loop_config=loop_config)


def run_worker_process(
    *,
    source: ConfigSource | None = None,
    worker_role: TaskType | None = None,
) -> None:
    """Bootstrap and run the worker process until shutdown."""
    from .runners import run_worker_process as _run

    _run(source=source, worker_role=worker_role)
