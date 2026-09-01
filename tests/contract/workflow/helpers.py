"""Shared contract-test helpers for workflow module (WF-014, LLD §14)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
from workflow import (
    ApprovalAction,
    TimelineEvent,
    TransitionRequest,
    TransitionSignal,
    WorkflowEngine,
    WorkflowState,
)

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)

_EVENT_TYPE_RANK = {
    "transition": 0,
    "task_enqueued": 1,
    "ai_invocation": 2,
}


@dataclass(frozen=True)
class MemoryWorkflowFixture:
    """Engine plus injectable fakes for contract assertions (LLD §14)."""

    engine: WorkflowEngine
    txn: object
    workflow_repo: object
    outbox_repo: object
    artifact_repo: object


def minimal_workflow_config(*, max_scenario_revisions: int = 2) -> AppConfig:
    """Valid AppConfig with configurable workflow domain."""
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
        collection=CollectionConfig(candidate_count=10, scoring=None),
        workflow=WorkflowConfig(max_scenario_revisions=max_scenario_revisions),
        workers=WorkerConfig(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(
                    initial_seconds=1.0,
                    multiplier=2.0,
                    max_seconds=30.0,
                ),
            ),
            TaskType.GENERATE_SCENARIO: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(
                    initial_seconds=1.0,
                    multiplier=2.0,
                    max_seconds=30.0,
                ),
            ),
        },
        timeouts={},
        failure_injection=FailureInjectionConfig(
            enabled=False,
            active_injections=frozenset(),
        ),
    )


def memory_workflow_engine(
    *,
    config: AppConfig | None = None,
) -> tuple[WorkflowEngine, object]:
    """Fixture seam per LLD §14 — boundary import allowed here only."""
    fixture = memory_workflow_fixture(config=config)
    return fixture.engine, fixture.txn


def memory_workflow_fixture(
    *,
    config: AppConfig | None = None,
) -> MemoryWorkflowFixture:
    """Engine with exposed fakes for outbox/artifact/timeline contract assertions."""
    from workflow.fakes.artifact import InMemoryArtifactRepo
    from workflow.fakes.outbox import InMemoryOutboxRepo
    from workflow.fakes.transaction import FakeTransactionManager
    from workflow.fakes.workflow import InMemoryWorkflowRepo
    from workflow.protocols import create_workflow_engine

    cfg = config or minimal_workflow_config()
    txn = FakeTransactionManager()
    workflow_repo = InMemoryWorkflowRepo()
    artifact_repo = InMemoryArtifactRepo()
    outbox_repo = InMemoryOutboxRepo()
    engine = create_workflow_engine(
        config=cfg,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        outbox_repo=outbox_repo,
        transaction_manager=txn,
    )
    return MemoryWorkflowFixture(
        engine=engine,
        txn=txn,
        workflow_repo=workflow_repo,
        outbox_repo=outbox_repo,
        artifact_repo=artifact_repo,
    )


def initiate_with_txn(
    engine: WorkflowEngine,
    txn: object,
    *,
    config: AppConfig,
) -> object:
    """Run initiate_workflow inside an active transaction."""
    with txn.transaction():  # type: ignore[attr-defined]
        return engine.initiate_workflow(config=config)


def transition_with_txn(
    engine: WorkflowEngine,
    txn: object,
    request: TransitionRequest,
) -> object:
    """Run apply_transition inside an active transaction."""
    with txn.transaction():  # type: ignore[attr-defined]
        return engine.apply_transition(request)


def approval_with_txn(
    engine: WorkflowEngine,
    txn: object,
    *,
    workflow_id: str,
    action: ApprovalAction,
) -> object:
    """Run apply_approval_action inside an active transaction."""
    with txn.transaction():  # type: ignore[attr-defined]
        return engine.apply_approval_action(workflow_id=workflow_id, action=action)


def stage_completed_request(
    *,
    workflow_id: str,
    expected_state: WorkflowState,
    reason: str = "stage_completed",
) -> TransitionRequest:
    """Build a STAGE_COMPLETED TransitionRequest."""
    return TransitionRequest(
        workflow_id=workflow_id,
        expected_state=expected_state,
        signal=TransitionSignal.STAGE_COMPLETED,
        reason=reason,
    )


def seed_workflow_awaiting_human_approval(
    engine: WorkflowEngine,
    txn: object,
    *,
    workflow_id: str,
) -> None:
    """Drive workflow through critic pass into AWAITING_HUMAN_APPROVAL (WF-TC-010/011)."""
    transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id=workflow_id,
            expected_state=WorkflowState.REVIEWING,
            signal=TransitionSignal.CRITIC_PASS,
            reason="critic_passed",
        ),
    )
    transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id=workflow_id,
            expected_state=WorkflowState.REVIEW_PASSED,
        ),
    )


def pending_outbox_for_workflow(outbox_repo: object, workflow_id: str) -> list[object]:
    """Return unpublished outbox rows for a workflow (LLD §14 OutboxRepo extension)."""
    return outbox_repo.list_unpublished_outbox_for_workflow(workflow_id)  # type: ignore[attr-defined]


def seed_output_package_artifacts(artifact_repo: object, *, workflow_id: str) -> None:
    """Seed active topic/scenario/critic artifacts for WF-TC-020 (LLD §8.2, §15)."""
    artifact_repo.seed_active_artifacts(  # type: ignore[attr-defined]
        workflow_id=workflow_id,
        topic={
            "selected_topic": "Robots learn empathy",
            "rationale": "Strong visual comedy potential",
            "confidence": 0.91,
        },
        scenario={
            "premise": "A robot attends art class",
            "characters": ["Unit-7", "Ms. Rivera"],
            "panels": [{"caption": "Brush meets circuit board"}],
            "punchline": "It paints a perfect error message",
        },
        critic={
            "verdict": "PASS",
            "dimensions": {"humor": 4, "clarity": 5},
        },
    )


def seed_timeline_collision_fixture(
    workflow_repo: object,
    artifact_repo: object,
    *,
    workflow_id: str,
) -> None:
    """Seed transitions/tasks/invocations with colliding occurred_at (WF-TC-022)."""
    workflow_repo.seed_timeline_collision(  # type: ignore[attr-defined]
        workflow_id=workflow_id,
        occurred_at=_FIXED_NOW,
        transition_ids=("tr-collision-002", "tr-collision-001"),
        task_ids=("task-collision-002", "task-collision-001"),
        invocation_ids=("inv-collision-002", "inv-collision-001"),
    )
    artifact_repo.seed_ai_invocations(  # type: ignore[attr-defined]
        workflow_id=workflow_id,
        occurred_at=_FIXED_NOW,
        invocation_ids=("inv-collision-002", "inv-collision-001"),
    )


def timeline_sort_key(event: TimelineEvent) -> tuple[object, ...]:
    """Derive LLD §8.4 sort key from a timeline event."""
    rank = getattr(event, "event_type_rank", _EVENT_TYPE_RANK.get(event.event_type, 99))
    stable_id = getattr(event, "stable_id", event.attributes.get("stable_id", ""))
    return (event.occurred_at, rank, stable_id)
