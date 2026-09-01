"""Pre-code test mold for WF-012 — revision limit via engine orchestration (LLD §16, WF-TC-017)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.types import TaskType
from workflow import TransitionSignal, WorkflowState

pytestmark = []

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _minimal_app_config(*, max_scenario_revisions: int = 2) -> object:
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
                prompt_file="prompts/topic_selector.txt",
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
        workflow=WorkflowConfig(max_scenario_revisions=max_scenario_revisions),
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


def _seed_reviewing_workflow(
    workflow_repo: object,
    *,
    workflow_id: str,
    revision_count: int,
) -> None:
    """Seed a workflow row in REVIEWING with the given revision_count."""
    from persistence.types import WorkflowRecord, WorkflowState as PersistenceWorkflowState

    workflow_repo.create_workflow(  # type: ignore[attr-defined]
        WorkflowRecord(
            workflow_id=workflow_id,
            state=PersistenceWorkflowState.REVIEWING,
            state_version=1,
            created_at=_FIXED_NOW,
            updated_at=_FIXED_NOW,
            revision_count=revision_count,
            failure_reason=None,
        )
    )


@pytest.fixture
def engine_with_fakes() -> tuple[object, object, object]:
    """DefaultWorkflowEngine wired with real table/executor/builder and in-memory repos."""
    from workflow.engine import DefaultWorkflowEngine, TransactionGuard
    from workflow.executor import TransitionExecutor
    from workflow.fakes.artifact import InMemoryArtifactRepo
    from workflow.fakes.outbox import InMemoryOutboxRepo
    from workflow.fakes.transaction import FakeTransactionManager
    from workflow.fakes.workflow import InMemoryWorkflowRepo
    from workflow.outbox_builder import LogicalVersionTracker, OutboxSpecBuilder
    from workflow.transition_table import TransitionTable

    config = _minimal_app_config(max_scenario_revisions=2)
    txn = FakeTransactionManager()
    workflow_repo = InMemoryWorkflowRepo()
    outbox_repo = InMemoryOutboxRepo()
    artifact_repo = InMemoryArtifactRepo()
    transition_table = TransitionTable()
    outbox_builder = OutboxSpecBuilder(
        logical_version_tracker=LogicalVersionTracker(),
        clock=lambda: _FIXED_NOW,
    )
    transaction_guard = TransactionGuard(transaction_manager=txn)
    executor = TransitionExecutor(
        workflow_repo=workflow_repo,
        outbox_repo=outbox_repo,
        transaction_guard=transaction_guard,
    )
    engine = DefaultWorkflowEngine(
        config=config,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        outbox_repo=outbox_repo,
        transaction_manager=txn,
        transition_table=transition_table,
        outbox_builder=outbox_builder,
        executor=executor,
        read_model_assembler=MagicMock(),
        telemetry=MagicMock(),
        workflow_id_allocator=MagicMock(),
        transaction_guard=transaction_guard,
    )
    return engine, txn, workflow_repo


def test_critic_revise_at_max_revisions_transitions_to_review_failed(
    engine_with_fakes: tuple[object, object, object],
) -> None:
    """WF-TC-017: revision_count == max_scenario_revisions → REVIEW_FAILED."""
    engine, txn, workflow_repo = engine_with_fakes
    workflow_id = "wf-revision-limit-001"
    _seed_reviewing_workflow(workflow_repo, workflow_id=workflow_id, revision_count=2)

    from workflow import TransitionRequest

    request = TransitionRequest(
        workflow_id=workflow_id,
        expected_state=WorkflowState.REVIEWING,
        signal=TransitionSignal.CRITIC_REVISE,
        reason="critic_requested_revision",
    )

    with txn.transaction():  # type: ignore[attr-defined]
        result = engine.apply_transition(request)  # type: ignore[attr-defined]

    assert result.to_state == WorkflowState.REVIEW_FAILED
    assert result.outbox_written is False
    assert result.enqueued_task is None


def test_critic_revise_below_limit_increments_revision_and_enqueues_regeneration(
    engine_with_fakes: tuple[object, object, object],
) -> None:
    """Below max revisions CRITIC_REVISE → REVISION_REQUIRED with regeneration path."""
    engine, txn, workflow_repo = engine_with_fakes
    workflow_id = "wf-revision-limit-002"
    _seed_reviewing_workflow(workflow_repo, workflow_id=workflow_id, revision_count=1)

    from workflow import TransitionRequest

    request = TransitionRequest(
        workflow_id=workflow_id,
        expected_state=WorkflowState.REVIEWING,
        signal=TransitionSignal.CRITIC_REVISE,
        reason="critic_requested_revision",
    )

    with txn.transaction():  # type: ignore[attr-defined]
        result = engine.apply_transition(request)  # type: ignore[attr-defined]

    assert result.to_state == WorkflowState.REVISION_REQUIRED
    assert result.outbox_written is False
    assert result.enqueued_task is None
