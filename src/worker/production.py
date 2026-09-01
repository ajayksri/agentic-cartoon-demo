"""Production worker dependency assembly (PD-001 / WKR-018, CG-RT-002)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from config.types import AgentId, AppConfig

from .handlers.collect import CollectTaskHandler
from .handlers.generate_scenario import GenerateScenarioTaskHandler
from .handlers.review_scenario import ReviewScenarioTaskHandler
from .handlers.select_topic import SelectTopicTaskHandler
from .protocols import (
    IdempotencyOrchestrator,
    TaskHandlerRegistry,
    create_idempotency_orchestrator,
    create_task_handler_registry,
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
    from persistence.protocols import IdempotencyRepo
    from providers.protocols import ModelProvider


@dataclass(frozen=True, slots=True)
class WorkerProductionDependencies:
    """Opaque production collaborators for runtime worker wiring (PD-001 / CG-RT-002)."""

    registry: TaskHandlerRegistry
    idempotency_orchestrator: IdempotencyOrchestrator
    collector: Collector
    topic_selection_agent: TopicSelectionAgent
    scenario_generation_agent: ScenarioGenerationAgent
    critic_agent: CriticAgent
    model_provider_factory: Callable[[AgentId], ModelProvider]


def _resolve_idempotency_repo(persistence_bundle: object) -> IdempotencyRepo:
    repo = getattr(persistence_bundle, "idempotency_repo", None)
    if repo is None:
        raise ValueError(
            "persistence_bundle.idempotency_repo is required for worker production wiring"
        )
    return repo  # type: ignore[no-any-return]


def _build_model_provider_factory(
    *,
    config: AppConfig,
    failure_injection: FailureInjectionRegistry,
) -> Callable[[AgentId], ModelProvider]:
    from providers import create_provider

    def factory(agent_id: AgentId) -> ModelProvider:
        agent_config = config.get_agent_config(agent_id)
        return create_provider(
            provider_id=agent_config.provider,
            config=config,
            registry=failure_injection,
        )

    return factory


def create_production_worker_dependencies(
    *,
    config: AppConfig,
    persistence_bundle: object,
    failure_injection: FailureInjectionRegistry,
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
) -> WorkerProductionDependencies:
    """Assemble production handlers, agents, collector, and provider factory (PD-001).

    Owns imports of ``agents``, ``collector``, and ``providers`` public surfaces so
    ``runtime`` never does. Registers COLLECT, SELECT_TOPIC, GENERATE_SCENARIO,
    REVIEW_SCENARIO handlers.
    """
    del logger, meter, tracer  # consumed by worker loop wiring, not factory assembly

    import agents
    import collector

    idempotency_orchestrator = create_idempotency_orchestrator(
        idempotency_repo=_resolve_idempotency_repo(persistence_bundle),
    )
    registry = create_task_handler_registry(
        handlers=(
            CollectTaskHandler(),
            SelectTopicTaskHandler(),
            GenerateScenarioTaskHandler(),
            ReviewScenarioTaskHandler(),
        ),
    )
    return WorkerProductionDependencies(
        registry=registry,
        idempotency_orchestrator=idempotency_orchestrator,
        collector=collector.create_collector(),
        topic_selection_agent=agents.create_topic_selection_agent(),
        scenario_generation_agent=agents.create_scenario_generation_agent(),
        critic_agent=agents.create_critic_agent(),
        model_provider_factory=_build_model_provider_factory(
            config=config,
            failure_injection=failure_injection,
        ),
    )
