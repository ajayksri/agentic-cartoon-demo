"""WKR-018 — production worker dependencies factory (PD-001)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from config.types import AgentId, TaskType
from persistence.fakes.idempotency import InMemoryIdempotencyRepo
from persistence.fakes.transaction import InMemoryTransactionManager
from worker import (
    WorkerProductionDependencies,
    create_production_worker_dependencies,
)
from worker.handlers.collect import CollectTaskHandler
from worker.handlers.generate_scenario import GenerateScenarioTaskHandler
from worker.handlers.review_scenario import ReviewScenarioTaskHandler
from worker.handlers.select_topic import SelectTopicTaskHandler

from tests.contract.worker.helpers import minimal_worker_config


class _PersistenceBundleStub:
    def __init__(self, idempotency_repo: object) -> None:
        self.idempotency_repo = idempotency_repo


@pytest.fixture(autouse=True)
def _fake_provider_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_API_KEY", os.environ.get("FAKE_API_KEY", "wkr-018-test-key"))
    monkeypatch.setenv("POSTGRES_USER", os.environ.get("POSTGRES_USER", "postgres"))
    monkeypatch.setenv("POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "postgres"))


def test_create_production_worker_dependencies_exported_on_public_surface() -> None:
    import worker

    assert "create_production_worker_dependencies" in worker.__all__
    assert "WorkerProductionDependencies" in worker.__all__
    assert callable(worker.create_production_worker_dependencies)


def test_factory_returns_all_fields_with_fake_provider() -> None:
    config = minimal_worker_config()
    txn = InMemoryTransactionManager()
    bundle = _PersistenceBundleStub(
        InMemoryIdempotencyRepo(transaction_manager=txn),
    )
    failure_injection = MagicMock()

    prod = create_production_worker_dependencies(
        config=config,
        persistence_bundle=bundle,
        failure_injection=failure_injection,
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
    )

    assert isinstance(prod, WorkerProductionDependencies)
    assert prod.registry is not None
    assert prod.idempotency_orchestrator is not None
    assert prod.collector is not None
    assert callable(getattr(prod.collector, "collect_stories", None))
    assert prod.topic_selection_agent is not None
    assert prod.scenario_generation_agent is not None
    assert prod.critic_agent is not None
    assert callable(prod.model_provider_factory)


def test_registry_resolves_all_four_v1_task_types() -> None:
    config = minimal_worker_config()
    txn = InMemoryTransactionManager()
    bundle = _PersistenceBundleStub(
        InMemoryIdempotencyRepo(transaction_manager=txn),
    )

    prod = create_production_worker_dependencies(
        config=config,
        persistence_bundle=bundle,
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
    )

    assert prod.registry.supported_task_types() == frozenset(TaskType)
    assert isinstance(prod.registry.get_handler(TaskType.COLLECT), CollectTaskHandler)
    assert isinstance(prod.registry.get_handler(TaskType.SELECT_TOPIC), SelectTopicTaskHandler)
    assert isinstance(
        prod.registry.get_handler(TaskType.GENERATE_SCENARIO),
        GenerateScenarioTaskHandler,
    )
    assert isinstance(
        prod.registry.get_handler(TaskType.REVIEW_SCENARIO),
        ReviewScenarioTaskHandler,
    )


def test_model_provider_factory_returns_fake_provider_per_agent() -> None:
    config = minimal_worker_config()
    txn = InMemoryTransactionManager()
    bundle = _PersistenceBundleStub(
        InMemoryIdempotencyRepo(transaction_manager=txn),
    )

    prod = create_production_worker_dependencies(
        config=config,
        persistence_bundle=bundle,
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
    )

    for agent_id in (AgentId.TOPIC_SELECTOR, AgentId.SCENARIO_GENERATOR, AgentId.CRITIC):
        provider = prod.model_provider_factory(agent_id)
        assert provider is not None
        first = prod.model_provider_factory(agent_id)
        second = prod.model_provider_factory(agent_id)
        assert first is not second
