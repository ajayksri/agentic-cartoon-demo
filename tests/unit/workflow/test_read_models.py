"""Unit tests for WF-009 — ReadModelAssembler (LLD §8)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from persistence.types import ArtifactType, WorkflowRecord, WorkflowState as PersistenceWorkflowState
from workflow import WorkflowState
from workflow.read_models import ReadModelAssembler

pytestmark = []

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
_WORKFLOW_ID = "wf-read-models-001"


def _workflow_record(*, state: WorkflowState = WorkflowState.APPROVED) -> WorkflowRecord:
    return WorkflowRecord(
        workflow_id=_WORKFLOW_ID,
        state=PersistenceWorkflowState(state.value),
        state_version=3,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        revision_count=1,
        failure_reason=None,
    )


@pytest.fixture
def assembler() -> ReadModelAssembler:
    return ReadModelAssembler(
        workflow_repo=MagicMock(),
        artifact_repo=MagicMock(),
    )


def test_assemble_output_package_keys_from_artifact_content(
    assembler: ReadModelAssembler,
) -> None:
    """Output package keys and nested fields match LLD §8.2 tables."""
    workflow = _workflow_record(state=WorkflowState.APPROVED)
    topic = MagicMock(
        artifact_id="art-topic",
        version=1,
        logical_version=1,
        created_at=_FIXED_NOW,
    )
    scenario = MagicMock(
        artifact_id="art-scenario",
        version=2,
        logical_version=2,
        created_at=_FIXED_NOW,
    )
    critic = MagicMock(
        artifact_id="art-critic",
        version=1,
        logical_version=1,
        created_at=_FIXED_NOW,
    )

    def active_side_effect(
        workflow_id: str, artifact_type: ArtifactType
    ) -> MagicMock | None:
        if artifact_type == ArtifactType.TOPIC_SELECTION:
            return topic
        if artifact_type == ArtifactType.SCENARIO:
            return scenario
        if artifact_type == ArtifactType.CRITIC_REVIEW:
            return critic
        return None

    assembler._artifact_repo.get_active_artifact.side_effect = active_side_effect
    assembler._artifact_repo.get_artifact_content.side_effect = lambda aid: {
        "art-topic": {
            "selected_topic": "Cats",
            "rationale": "Popular",
            "confidence": 0.9,
        },
        "art-scenario": {
            "premise": "A cat nap",
            "characters": ["Milo"],
            "panels": [{"id": 1}],
            "punchline": "Meow",
        },
        "art-critic": {
            "verdict": "pass",
            "dimensions": {"humor": 5},
        },
    }[aid]
    assembler._workflow_repo.list_transitions.return_value = []
    assembler._artifact_repo.list_ai_invocations.return_value = []

    output = assembler.assemble_output(workflow=workflow)

    assert output.is_complete is True
    assert "topic" in output.package
    assert "scenario" in output.package
    assert "critic" in output.package
    assert "execution" in output.package
    assert output.package["topic"]["selected_topic"] == "Cats"
    assert output.package["scenario"]["panels"] == [{"id": 1}]
    assert output.package["execution"]["transition_count"] == 0


def test_assemble_output_terminal_failure_sets_incomplete_with_default_reason(
    assembler: ReadModelAssembler,
) -> None:
    """Terminal non-APPROVED states set is_complete=False with default failure code."""
    workflow = _workflow_record(state=WorkflowState.FAILED)
    workflow = WorkflowRecord(
        workflow_id=workflow.workflow_id,
        state=workflow.state,
        state_version=workflow.state_version,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        revision_count=workflow.revision_count,
        failure_reason=None,
    )
    assembler._artifact_repo.get_active_artifact.return_value = None
    assembler._workflow_repo.list_transitions.return_value = []
    assembler._artifact_repo.list_ai_invocations.return_value = []

    output = assembler.assemble_output(workflow=workflow)

    assert output.is_complete is False
    assert output.failure_reason == "failed"


def test_assemble_timeline_sorts_by_occurred_at_rank_and_stable_id(
    assembler: ReadModelAssembler,
) -> None:
    """Timeline ordering: transition before task before invocation at same timestamp."""
    transition = MagicMock(
        transition_id="tr-1",
        from_state=MagicMock(value="COLLECTING"),
        to_state=MagicMock(value="COLLECTED"),
        reason="stage_completed",
        occurred_at=_FIXED_NOW,
    )
    task = MagicMock(
        task_id="task-1",
        task_type=MagicMock(value="SELECT_TOPIC"),
        attempt=1,
        created_at=_FIXED_NOW,
    )
    invocation = MagicMock(
        invocation_id="inv-1",
        agent_name="critic",
        status=MagicMock(value="completed"),
        started_at=_FIXED_NOW,
    )

    assembler._workflow_repo.list_transitions.return_value = [transition]
    assembler._workflow_repo.list_tasks_for_workflow.return_value = [task]
    assembler._artifact_repo.list_ai_invocations.return_value = [invocation]

    timeline = assembler.assemble_timeline(workflow_id=_WORKFLOW_ID)

    assert [event.event_type for event in timeline.events] == [
        "transition",
        "task_enqueued",
        "ai_invocation",
    ]


def test_assemble_timeline_uses_artifact_repo_for_invocations(
    assembler: ReadModelAssembler,
) -> None:
    """Timeline merge calls artifact_repo.list_ai_invocations, not WorkflowRepo."""
    assembler._workflow_repo.list_transitions.return_value = []
    assembler._workflow_repo.list_tasks_for_workflow.return_value = []
    assembler._artifact_repo.list_ai_invocations.return_value = []

    assembler.assemble_timeline(workflow_id=_WORKFLOW_ID)

    assembler._artifact_repo.list_ai_invocations.assert_called_once_with(_WORKFLOW_ID)
