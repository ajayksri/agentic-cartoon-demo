"""Execution context builders (LLD §4.7–§4.8)."""

from __future__ import annotations

from collections.abc import Callable

from agents.types import AgentRunContext
from config.types import AgentId, AppConfig
from observability.protocols import Logger, Meter, Tracer
from persistence.protocols import (
    ArtifactRepo,
    TransactionManager,
    WorkflowRepo,
)
from persistence.types import TaskRecord
from providers.protocols import ModelProvider
from task_queue.types import PendingDelivery

from .protocols import IdempotencyOrchestrator
from .types import TaskExecutionContext, TaskTiming


class TaskExecutionContextBuilder:
    """Assembles frozen TaskExecutionContext instances."""

    @staticmethod
    def build(
        *,
        worker_id: str,
        config: AppConfig,
        delivery: PendingDelivery,
        task_record: TaskRecord,
        idempotency_key: str,
        timing: TaskTiming,
        workflow_engine: object,
        workflow_repo: WorkflowRepo,
        artifact_repo: ArtifactRepo,
        idempotency_orchestrator: IdempotencyOrchestrator,
        transaction_manager: TransactionManager,
        failure_injection: object,
        logger: Logger,
        meter: Meter,
        tracer: Tracer,
        collector: object,
        topic_selection_agent: object,
        scenario_generation_agent: object,
        critic_agent: object,
        model_provider_factory: Callable[[AgentId], ModelProvider],
    ) -> TaskExecutionContext:
        return TaskExecutionContext(
            worker_id=worker_id,
            config=config,
            delivery=delivery,
            task_record=task_record,
            idempotency_key=idempotency_key,
            timing=timing,
            workflow_engine=workflow_engine,
            workflow_repo=workflow_repo,
            artifact_repo=artifact_repo,
            idempotency_orchestrator=idempotency_orchestrator,
            transaction_manager=transaction_manager,
            failure_injection=failure_injection,
            logger=logger,
            meter=meter,
            tracer=tracer,
            collector=collector,
            topic_selection_agent=topic_selection_agent,
            scenario_generation_agent=scenario_generation_agent,
            critic_agent=critic_agent,
            model_provider_factory=model_provider_factory,
        )


class AgentRunContextBuilder:
    """Builds AgentRunContext for agent stage invocations."""

    @staticmethod
    def build(
        *,
        agent_id: AgentId,
        delivery: PendingDelivery,
        config: AppConfig,
        model_provider_factory: Callable[[AgentId], ModelProvider],
        logger: Logger,
        meter: Meter,
        tracer: Tracer,
        attempt: int,
    ) -> AgentRunContext:
        provider = model_provider_factory(agent_id)
        return AgentRunContext(
            agent_id=agent_id,
            workflow_id=delivery.message.workflow_id,
            task_id=delivery.message.task_id,
            task_attempt=attempt,
            config=config,
            provider=provider,
            logger=logger,
            meter=meter,
            tracer=tracer,
        )
