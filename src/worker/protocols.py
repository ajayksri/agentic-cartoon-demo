"""Public worker protocol definitions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from config.types import AgentId, AppConfig, TaskType
from persistence.types import IdempotencyInsertSpec

from .types import (
    IdempotencyCheckResult,
    IdempotencyClaimResult,
    TaskExecutionContext,
    TaskHandlerResult,
    WorkerLoopConfig,
)

if TYPE_CHECKING:
    from agents.protocols import (
        CriticAgent,
        ScenarioGenerationAgent,
        TopicSelectionAgent,
    )
    from collector.protocols import Collector
    from failure_injection.protocols import FailureInjectionRegistry
    from observability.protocols import Logger, Meter, Tracer
    from persistence.protocols import (
        ArtifactRepo,
        IdempotencyRepo,
        TaskLeaseRepo,
        TransactionManager,
        WorkflowRepo,
    )
    from providers.protocols import ModelProvider
    from task_queue.protocols import TaskQueue
    from workflow.protocols import WorkflowEngine


@runtime_checkable
class TaskHandler(Protocol):
    """Stage-specific task execution for one TaskType (ADR-005)."""

    @property
    def task_type(self) -> TaskType:
        """Task type this handler supports."""
        ...

    def handle(self, context: TaskExecutionContext) -> TaskHandlerResult:
        """Execute one dequeued task stage without calling apply_transition or ack."""
        ...


@runtime_checkable
class TaskHandlerRegistry(Protocol):
    """Registry of TaskHandler instances keyed by TaskType."""

    def register(self, handler: TaskHandler) -> None:
        """Register a handler; raises DuplicateHandlerError on duplicate task_type."""
        ...

    def get_handler(self, task_type: TaskType) -> TaskHandler:
        """Return handler for task_type; raises HandlerNotFoundError when missing."""
        ...

    def supported_task_types(self) -> frozenset[TaskType]:
        """Return registered task types."""
        ...


@runtime_checkable
class IdempotencyOrchestrator(Protocol):
    """Coordinates idempotency pre-checks and completion claims (ACD-FR-015/016)."""

    def check_before_execution(
        self, *, idempotency_key: str
    ) -> IdempotencyCheckResult:
        """Lookup existing completion; short-circuit redeliveries when already done."""
        ...

    def claim_completion(
        self, *, spec: IdempotencyInsertSpec
    ) -> IdempotencyClaimResult:
        """Insert-once completion record; detect duplicate concurrent commits."""
        ...

    def build_idempotency_key(
        self,
        *,
        workflow_id: str,
        task_type: TaskType,
        logical_version: int,
    ) -> str:
        """Compose stable idempotency key (CG-WKR-001 / OPEN-004)."""
        ...


@runtime_checkable
class WorkerLoop(Protocol):
    """Long-running task consume/process loop (ACD-FR-044)."""

    def run(self) -> None:
        """Block processing tasks until stop() or fatal error."""
        ...

    def stop(self) -> None:
        """Request graceful shutdown after in-flight tasks complete."""
        ...


def create_task_handler_registry(
    *,
    handlers: Sequence[TaskHandler],
) -> TaskHandlerRegistry:
    """Build registry from handler instances."""
    from .registry import create_task_handler_registry as _create

    return _create(handlers=handlers)


def create_idempotency_orchestrator(
    *,
    idempotency_repo: IdempotencyRepo,
) -> IdempotencyOrchestrator:
    """Factory for the default IdempotencyOrchestrator implementation."""
    from .idempotency import create_idempotency_orchestrator as _create

    return _create(idempotency_repo=idempotency_repo)


def create_worker_loop(
    *,
    config: AppConfig,
    loop_config: WorkerLoopConfig,
    registry: TaskHandlerRegistry,
    task_queue: TaskQueue,
    task_lease_repo: TaskLeaseRepo,
    workflow_engine: WorkflowEngine,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    idempotency_orchestrator: IdempotencyOrchestrator,
    transaction_manager: TransactionManager,
    failure_injection: FailureInjectionRegistry,
    collector: Collector,
    topic_selection_agent: TopicSelectionAgent,
    scenario_generation_agent: ScenarioGenerationAgent,
    critic_agent: CriticAgent,
    model_provider_factory: Callable[[AgentId], ModelProvider],
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
) -> WorkerLoop:
    """Create the default WorkerLoop implementation for the composition root."""
    from .loop import create_worker_loop as _create

    return _create(
        config=config,
        loop_config=loop_config,
        registry=registry,
        task_queue=task_queue,
        task_lease_repo=task_lease_repo,
        workflow_engine=workflow_engine,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_orchestrator=idempotency_orchestrator,
        transaction_manager=transaction_manager,
        failure_injection=failure_injection,
        collector=collector,
        topic_selection_agent=topic_selection_agent,
        scenario_generation_agent=scenario_generation_agent,
        critic_agent=critic_agent,
        model_provider_factory=model_provider_factory,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )


def run_task_loop(
    *,
    config: AppConfig,
    loop_config: WorkerLoopConfig,
    registry: TaskHandlerRegistry,
    task_queue: TaskQueue,
    task_lease_repo: TaskLeaseRepo,
    workflow_engine: WorkflowEngine,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    idempotency_orchestrator: IdempotencyOrchestrator,
    transaction_manager: TransactionManager,
    failure_injection: FailureInjectionRegistry,
    collector: Collector,
    topic_selection_agent: TopicSelectionAgent,
    scenario_generation_agent: ScenarioGenerationAgent,
    critic_agent: CriticAgent,
    model_provider_factory: Callable[[AgentId], ModelProvider],
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
) -> None:
    """Create and run the worker loop until shutdown (worker process entrypoint)."""
    from .loop import run_task_loop as _run

    _run(
        config=config,
        loop_config=loop_config,
        registry=registry,
        task_queue=task_queue,
        task_lease_repo=task_lease_repo,
        workflow_engine=workflow_engine,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_orchestrator=idempotency_orchestrator,
        transaction_manager=transaction_manager,
        failure_injection=failure_injection,
        collector=collector,
        topic_selection_agent=topic_selection_agent,
        scenario_generation_agent=scenario_generation_agent,
        critic_agent=critic_agent,
        model_provider_factory=model_provider_factory,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )
