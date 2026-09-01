"""Unit tests for WKR-011–014 handler mapping (LLD §4.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.types import CriticStatus, TopicSelectionOutcome
from collector.errors import CollectorFetchError
from config.types import AgentId, ProviderId, TaskType
from persistence.types import ArtifactRecord, ArtifactType, PayloadReference, TaskRecord, TaskStatus, TaskType as PersTaskType
from workflow.types import TransitionSignal

from worker.handlers.collect import CollectTaskHandler
from worker.handlers.generate_scenario import GenerateScenarioTaskHandler
from worker.handlers.review_scenario import ReviewScenarioTaskHandler
from worker.handlers.select_topic import SelectTopicTaskHandler

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _invocation_record() -> SimpleNamespace:
    return SimpleNamespace(invocation_id="inv-1")


def _artifact_record(artifact_type: ArtifactType, artifact_id: str = "art-1") -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=artifact_id,
        workflow_id="wf-1",
        artifact_type=artifact_type,
        name=artifact_type.value,
        version=1,
        logical_version=1,
        is_active=True,
        created_at=_FIXED_NOW,
    )


def _base_context(**overrides: object) -> SimpleNamespace:
    artifact_repo = MagicMock()
    artifact_repo.create_artifact.return_value = "art-out"
    artifact_repo.get_active_artifact.return_value = None
    txn = MagicMock()
    txn.is_in_transaction.return_value = True
    failure_injection = MagicMock()
    failure_injection.invoke_if_active.return_value = True
    provider = SimpleNamespace(provider_id=ProviderId.FAKE)
    base = SimpleNamespace(
        config=SimpleNamespace(
            get_agent_config=lambda _aid: SimpleNamespace(model="fake-model"),
        ),
        delivery=SimpleNamespace(
            message=SimpleNamespace(
                workflow_id="wf-1",
                task_id="task-1",
                task_type=TaskType.GENERATE_SCENARIO,
                attempt=1,
            ),
        ),
        task_record=TaskRecord(
            task_id="task-1",
            workflow_id="wf-1",
            task_type=PersTaskType.GENERATE_SCENARIO,
            attempt=1,
            status=TaskStatus.DISPATCHED,
            payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
            idempotency_key="idem-1",
            created_at=_FIXED_NOW,
            updated_at=_FIXED_NOW,
        ),
        workflow_repo=MagicMock(),
        workflow_engine=MagicMock(),
        artifact_repo=artifact_repo,
        transaction_manager=txn,
        failure_injection=failure_injection,
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        model_provider_factory=lambda _aid: provider,
        collector=SimpleNamespace(
            collect_stories=lambda **_kw: SimpleNamespace(
                stories=(),
                stats=SimpleNamespace(total_fetched=0, accepted=0, rejected=0),
            ),
        ),
        topic_selection_agent=MagicMock(),
        scenario_generation_agent=MagicMock(),
        critic_agent=MagicMock(),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_collect_handler_signal_and_artifact_type() -> None:
    handler = CollectTaskHandler()
    assert handler.task_type == TaskType.COLLECT
    context = _base_context()
    result = handler.handle(context)  # type: ignore[arg-type]
    assert result.transition_signal == TransitionSignal.STAGE_COMPLETED
    spec = context.artifact_repo.create_artifact.call_args.args[0]
    assert spec.artifact_type == ArtifactType.COLLECTED_STORIES


def test_collect_handler_propagates_collector_error() -> None:
    error = CollectorFetchError("fetch failed")

    def _raising_collect(**_kw: object) -> object:
        raise error

    context = _base_context(
        collector=SimpleNamespace(collect_stories=_raising_collect),
    )
    with pytest.raises(CollectorFetchError) as exc_info:
        CollectTaskHandler().handle(context)  # type: ignore[arg-type]
    assert exc_info.value is error


def test_collect_handler_does_not_call_apply_transition() -> None:
    workflow_engine = MagicMock()
    context = _base_context(workflow_engine=workflow_engine)
    CollectTaskHandler().handle(context)  # type: ignore[arg-type]
    workflow_engine.apply_transition.assert_not_called()


@pytest.mark.parametrize(
    ("outcome", "expected_signal"),
    [
        (TopicSelectionOutcome.TOPIC_SELECTED, TransitionSignal.STAGE_COMPLETED),
        (TopicSelectionOutcome.NO_SUITABLE_TOPIC, TransitionSignal.NO_SUITABLE_TOPIC),
    ],
)
def test_select_topic_handler_signals(
    outcome: TopicSelectionOutcome,
    expected_signal: TransitionSignal,
) -> None:
    handler = SelectTopicTaskHandler()
    assert handler.task_type == TaskType.SELECT_TOPIC
    collected = _artifact_record(ArtifactType.COLLECTED_STORIES)
    artifact_repo = MagicMock()
    artifact_repo.get_active_artifact.return_value = collected
    artifact_repo.get_artifact_content.return_value = {"schema_version": 1, "candidates": []}
    artifact_repo.create_artifact.return_value = "art-topic"
    artifact_repo.append_ai_invocation.return_value = _invocation_record()
    context = _base_context(
        artifact_repo=artifact_repo,
        topic_selection_agent=SimpleNamespace(
            run=lambda **_kw: SimpleNamespace(
                outcome=outcome,
                prompt_version="v1",
                selected_topic="topic" if outcome == TopicSelectionOutcome.TOPIC_SELECTED else None,
            ),
        ),
    )
    context.transaction_manager = MagicMock()
    context.transaction_manager.is_in_transaction.return_value = True
    result = handler.handle(context)  # type: ignore[arg-type]
    assert result.transition_signal == expected_signal
    spec = context.artifact_repo.create_artifact.call_args.args[0]
    assert spec.artifact_type == ArtifactType.TOPIC_SELECTION


def test_generate_scenario_handler_signal() -> None:
    handler = GenerateScenarioTaskHandler()
    assert handler.task_type == TaskType.GENERATE_SCENARIO
    topic = _artifact_record(ArtifactType.TOPIC_SELECTION)
    artifact_repo = MagicMock()
    artifact_repo.get_active_artifact.return_value = topic
    artifact_repo.get_artifact_content.return_value = {
        "schema_version": 1,
        "outcome": "topic_selected",
        "selected_topic": "topic",
        "why_interesting": "because it is funny",
        "cartoon_angle": "developer irony",
    }
    artifact_repo.create_artifact.return_value = "art-scenario"
    artifact_repo.append_ai_invocation.return_value = _invocation_record()
    context = _base_context(
        artifact_repo=artifact_repo,
        scenario_generation_agent=SimpleNamespace(
            run=lambda **_kw: SimpleNamespace(
                topic="topic",
                premise="premise",
                characters=(),
                panels=(),
                punchline="punch",
                prompt_version="v1",
            ),
        ),
    )
    context.transaction_manager = MagicMock()
    context.transaction_manager.is_in_transaction.return_value = True
    result = handler.handle(context)  # type: ignore[arg-type]
    assert result.transition_signal == TransitionSignal.STAGE_COMPLETED
    spec = context.artifact_repo.create_artifact.call_args.args[0]
    assert spec.artifact_type == ArtifactType.SCENARIO
    assert spec.content["topic"]["why_interesting"] == "because it is funny"
    assert spec.content["topic"]["cartoon_angle"] == "developer irony"


@pytest.mark.parametrize(
    ("status", "expected_signal"),
    [
        (CriticStatus.PASS, TransitionSignal.CRITIC_PASS),
        (CriticStatus.REVISE, TransitionSignal.CRITIC_REVISE),
    ],
)
def test_review_scenario_handler_signals(
    status: CriticStatus,
    expected_signal: TransitionSignal,
) -> None:
    handler = ReviewScenarioTaskHandler()
    assert handler.task_type == TaskType.REVIEW_SCENARIO
    scenario = _artifact_record(ArtifactType.SCENARIO)
    artifact_repo = MagicMock()
    artifact_repo.get_active_artifact.return_value = scenario
    artifact_repo.get_artifact_content.return_value = {
        "schema_version": 1,
        "topic": {"selected_topic": "topic"},
        "premise": "premise",
        "characters": [],
        "panels": [],
    }
    artifact_repo.create_artifact.return_value = "art-review"
    artifact_repo.append_ai_invocation.return_value = _invocation_record()
    context = _base_context(
        workflow_repo=MagicMock(
            get_workflow=MagicMock(return_value=SimpleNamespace(revision_count=1)),
        ),
        artifact_repo=artifact_repo,
        critic_agent=SimpleNamespace(
            run=lambda **_kw: SimpleNamespace(
                status=status,
                issues=(),
                prompt_version="v1",
            ),
        ),
    )
    context.transaction_manager = MagicMock()
    context.transaction_manager.is_in_transaction.return_value = True
    result = handler.handle(context)  # type: ignore[arg-type]
    assert result.transition_signal == expected_signal
    spec = context.artifact_repo.create_artifact.call_args.args[0]
    assert spec.artifact_type == ArtifactType.CRITIC_REVIEW
