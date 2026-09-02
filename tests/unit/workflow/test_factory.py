"""Smoke tests for WF-013 — create_workflow_engine factory wiring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config import (
    AgentConfig,
    AgentId,
    AppConfig,
    BackoffConfig,
    CollectionConfig,
    FailureInjectionConfig,
    InfrastructureConfig,
    PostgresConfig,
    ProviderConfig,
    ProviderId,
    RedisConfig,
    RetryPolicy,
    TaskType,
    WorkerConfig,
    WorkflowConfig,
)
from workflow import create_workflow_engine
from workflow.fakes.artifact import InMemoryArtifactRepo
from workflow.fakes.outbox import InMemoryOutboxRepo
from workflow.fakes.transaction import FakeTransactionManager
from workflow.fakes.workflow import InMemoryWorkflowRepo

pytestmark = []

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _minimal_config() -> AppConfig:
    return AppConfig(
        infrastructure=InfrastructureConfig(
            postgres=PostgresConfig(
                host="localhost",
                port=5432,
                database="test",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisConfig(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentConfig(
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/topic_selector/v1.txt",
            ),
        },
        providers={
            ProviderId.GEMINI: ProviderConfig(
                api_key_env="GEMINI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionConfig(candidate_count=5, scoring=None),
        workflow=WorkflowConfig(max_scenario_revisions=2),
        workers=WorkerConfig(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0),
            ),
        },
        timeouts={},
        failure_injection=FailureInjectionConfig(enabled=False, active_injections=frozenset()),
    )


def test_create_workflow_engine_returns_workflow_engine_protocol() -> None:
    """Factory builds engine satisfying WorkflowEngine with scanner wired."""
    config = _minimal_config()
    txn = FakeTransactionManager()
    engine = create_workflow_engine(
        config=config,
        workflow_repo=InMemoryWorkflowRepo(),
        artifact_repo=InMemoryArtifactRepo(),
        outbox_repo=InMemoryOutboxRepo(),
        transaction_manager=txn,
    )

    for method in (
        "initiate_workflow",
        "apply_transition",
        "apply_approval_action",
        "reconcile_stuck_workflows",
        "get_workflow_status",
        "get_workflow_history",
        "get_workflow_output",
        "get_workflow_timeline",
    ):
        assert hasattr(engine, method)
    assert engine._reconciliation_scanner is not None  # type: ignore[attr-defined]


def test_create_workflow_engine_initiate_smoke() -> None:
    """Smoke: factory-built engine can initiate workflow inside a transaction."""
    config = _minimal_config()
    txn = FakeTransactionManager()
    engine = create_workflow_engine(
        config=config,
        workflow_repo=InMemoryWorkflowRepo(),
        artifact_repo=InMemoryArtifactRepo(),
        outbox_repo=InMemoryOutboxRepo(),
        transaction_manager=txn,
    )

    with txn.transaction():
        result = engine.initiate_workflow(config=config)

    assert result.workflow_id
    assert result.state.value == "COLLECTING"
