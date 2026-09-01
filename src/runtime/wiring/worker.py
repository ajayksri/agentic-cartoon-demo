"""Worker process wiring (LLD §13, CG-RT-002)."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config.types import AppConfig, TaskType
from worker.protocols import create_worker_loop

from ..bootstrap import BootstrapContext
from ..constants import (
    DEFAULT_WORKER_BLOCK_MS,
    DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
    WORKER_GROUP_BY_TASK_TYPE,
    WORKER_STREAM_BY_TASK_TYPE,
)
from ..errors import DependencyWiringError
from ..settings import WorkerProcessConfig
from ..types import WiredDependencies

WorkerDependenciesFactory = Callable[..., "WorkerProductionDependencies"]
WorkerLoopFactory = Callable[..., object]


@dataclass(frozen=True, slots=True)
class WorkerProductionDependencies:
    """Opaque worker-owned collaborators assembled outside runtime forbidden imports."""

    registry: object
    idempotency_orchestrator: object
    collector: object
    topic_selection_agent: object
    scenario_generation_agent: object
    critic_agent: object
    model_provider_factory: object


def build_worker_loop_config(role: TaskType) -> Any:
    """Map worker role to stream/group consumer settings (HLD §6.2)."""
    from worker.types import WorkerLoopConfig

    return WorkerLoopConfig(
        stream=WORKER_STREAM_BY_TASK_TYPE[role],
        consumer_group=WORKER_GROUP_BY_TASK_TYPE[role],
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
        block_ms=DEFAULT_WORKER_BLOCK_MS,
        shutdown_grace_seconds=DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
    )


def _default_worker_dependencies_factory(
    *,
    entry: object,
    config: AppConfig,
    persistence_bundle: object,
    failure_injection: object,
    logger: object,
    meter: object,
    tracer: object,
) -> WorkerProductionDependencies:
    try:
        import worker as worker_module
    except ImportError as exc:
        raise DependencyWiringError(
            "worker.create_production_worker_dependencies unavailable (LLD-RT-001)",
            entry=entry,  # type: ignore[arg-type]
            dependency="worker",
        ) from exc

    factory = getattr(worker_module, "create_production_worker_dependencies", None)
    if factory is None:
        raise DependencyWiringError(
            "worker.create_production_worker_dependencies unavailable (LLD-RT-001)",
            entry=entry,  # type: ignore[arg-type]
            dependency="worker",
        )

    prod = factory(
        config=config,
        persistence_bundle=persistence_bundle,
        failure_injection=failure_injection,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )
    return WorkerProductionDependencies(
        registry=prod.registry,
        idempotency_orchestrator=prod.idempotency_orchestrator,
        collector=prod.collector,
        topic_selection_agent=prod.topic_selection_agent,
        scenario_generation_agent=prod.scenario_generation_agent,
        critic_agent=prod.critic_agent,
        model_provider_factory=prod.model_provider_factory,
    )


class WorkerProcessWiring:
    """Builds WorkerLoopConfig and invokes worker factories without forbidden imports."""

    def wire(
        self,
        ctx: BootstrapContext,
        *,
        worker_config: WorkerProcessConfig | None = None,
        worker_dependencies_factory: WorkerDependenciesFactory | None = None,
        worker_loop_factory: WorkerLoopFactory | None = None,
    ) -> BootstrapContext:
        process_config = worker_config or WorkerProcessConfig()
        loop_config = build_worker_loop_config(process_config.worker_role)
        deps_factory = worker_dependencies_factory or _default_worker_dependencies_factory
        loop_factory = worker_loop_factory or create_worker_loop

        production = deps_factory(
            entry=ctx.entry,
            config=ctx.config,
            persistence_bundle=ctx.bundle,
            failure_injection=ctx.failure_injection,
            logger=ctx.logger,
            meter=ctx.meter,
            tracer=ctx.tracer,
        )

        worker_loop = loop_factory(
            config=ctx.config,
            loop_config=loop_config,
            registry=production.registry,
            task_queue=ctx.task_queue,
            task_lease_repo=ctx.bundle.task_lease_repo,
            workflow_engine=ctx.workflow_engine,
            workflow_repo=ctx.bundle.workflow_repo,
            artifact_repo=ctx.bundle.artifact_repo,
            idempotency_orchestrator=production.idempotency_orchestrator,
            transaction_manager=ctx.bundle.transaction_manager,
            failure_injection=ctx.failure_injection,
            collector=production.collector,
            topic_selection_agent=production.topic_selection_agent,
            scenario_generation_agent=production.scenario_generation_agent,
            critic_agent=production.critic_agent,
            model_provider_factory=production.model_provider_factory,
            logger=ctx.logger,
            meter=ctx.meter,
            tracer=ctx.tracer,
        )

        ctx.wired = WiredDependencies(
            entry=ctx.entry,
            config=ctx.config,
            workflow_engine=ctx.workflow_engine,
            task_queue=ctx.task_queue,
            worker_loop=worker_loop,
        )
        return ctx
