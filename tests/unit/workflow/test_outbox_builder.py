"""Pre-code test mold for WF-005 — OutboxSpecBuilder (LLD §4)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.types import TaskType

pytestmark = []

_FIXED_CLOCK = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
_WORKFLOW_ID = "wf-outbox-test-001"


@pytest.fixture
def outbox_builder() -> object:
    from workflow.outbox_builder import LogicalVersionTracker, OutboxSpecBuilder

    return OutboxSpecBuilder(
        logical_version_tracker=LogicalVersionTracker(),
        clock=lambda: _FIXED_CLOCK,
    )


@pytest.fixture
def workflow_record() -> object:
    from persistence.types import WorkflowRecord, WorkflowState as PersistenceWorkflowState

    return WorkflowRecord(
        workflow_id=_WORKFLOW_ID,
        state=PersistenceWorkflowState.COLLECTING,
        state_version=1,
        created_at=_FIXED_CLOCK,
        updated_at=_FIXED_CLOCK,
        revision_count=0,
        failure_reason=None,
    )


@pytest.mark.parametrize(
    ("task_type", "logical_version", "expected_key"),
    [
        (TaskType.COLLECT, 1, f"{_WORKFLOW_ID}:COLLECT:1"),
        (TaskType.SELECT_TOPIC, 1, f"{_WORKFLOW_ID}:SELECT_TOPIC:1"),
        (TaskType.GENERATE_SCENARIO, 2, f"{_WORKFLOW_ID}:GENERATE_SCENARIO:2"),
        (TaskType.REVIEW_SCENARIO, 1, f"{_WORKFLOW_ID}:REVIEW_SCENARIO:1"),
    ],
)
def test_format_idempotency_key_matches_lld(
    task_type: TaskType,
    logical_version: int,
    expected_key: str,
) -> None:
    """Idempotency key format per LLD §4.2."""
    from workflow.outbox_builder import format_idempotency_key

    assert (
        format_idempotency_key(
            workflow_id=_WORKFLOW_ID,
            task_type=task_type,
            logical_version=logical_version,
        )
        == expected_key
    )


@pytest.mark.parametrize(
    ("task_type", "logical_version", "expected_payload"),
    [
        (TaskType.COLLECT, 1, {}),
        (TaskType.SELECT_TOPIC, 1, {}),
        (TaskType.GENERATE_SCENARIO, 2, {"logical_version": 2}),
        (TaskType.REVIEW_SCENARIO, 1, {"logical_version": 1}),
    ],
)
def test_build_payload_json_per_task_type(
    outbox_builder: object,
    workflow_record: object,
    task_type: TaskType,
    logical_version: int,
    expected_payload: dict[str, object],
) -> None:
    """Payload JSON matches LLD §4.3 table."""
    result = outbox_builder.build(  # type: ignore[attr-defined]
        workflow=workflow_record,
        task_type=task_type,
        logical_version=logical_version,
        attempt=1,
    )

    assert result.payload_json == expected_payload


def test_build_generates_required_fields(
    outbox_builder: object,
    workflow_record: object,
) -> None:
    """OutboxBuildResult contains task spec, record, insert, and payload."""
    result = outbox_builder.build(  # type: ignore[attr-defined]
        workflow=workflow_record,
        task_type=TaskType.COLLECT,
        logical_version=1,
        attempt=1,
    )

    assert result.task_spec.workflow_id == _WORKFLOW_ID
    assert result.task_spec.task_type == TaskType.COLLECT
    assert result.task_spec.attempt == 1
    assert result.task_spec.idempotency_key == f"{_WORKFLOW_ID}:COLLECT:1"
    assert result.task_spec.created_at == _FIXED_CLOCK
    assert result.task_spec.payload_reference == result.task_spec.task_id
    assert result.task_record.status.value == "PENDING"
    assert result.outbox_insert.task_id == result.task_spec.task_id


def test_build_for_decision_returns_none_when_no_outbox_task_type(
    outbox_builder: object,
    workflow_record: object,
) -> None:
    """build_for_decision returns None when decision.outbox_task_type is None."""
    from workflow.transition_table import TransitionDecision
    from workflow import TransitionSignal, WorkflowState

    decision = TransitionDecision(
        from_state=WorkflowState.COLLECTED,
        to_state=WorkflowState.SELECTING_TOPIC,
        signal=TransitionSignal.STAGE_COMPLETED,
        outbox_task_type=None,
    )
    artifact_repo = MagicMock()

    result = outbox_builder.build_for_decision(  # type: ignore[attr-defined]
        workflow=workflow_record,
        decision=decision,
        artifact_repo=artifact_repo,
    )

    assert result is None
