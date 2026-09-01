"""Pre-code test mold for WKR-006 — WorkflowStateGuard (LLD §4.9)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from workflow.types import TransitionSignal, WorkflowState


def _guard() -> object:
    from worker.state_mapping import WorkflowStateGuard

    return WorkflowStateGuard()


@pytest.mark.parametrize(
    ("task_type", "expected"),
    [
        (TaskType.COLLECT, WorkflowState.COLLECTING),
        (TaskType.SELECT_TOPIC, WorkflowState.SELECTING_TOPIC),
        (TaskType.GENERATE_SCENARIO, WorkflowState.GENERATING_SCENARIO),
        (TaskType.REVIEW_SCENARIO, WorkflowState.REVIEWING),
    ],
)
def test_expected_state_for_task_type(task_type: TaskType, expected: WorkflowState) -> None:
    from worker.state_mapping import WorkflowStateGuard

    assert WorkflowStateGuard.expected_state_for_task(task_type) == expected


@pytest.mark.wkr_tc("032")
def test_classify_stale_task_approval_wait() -> None:
    """WKR-TC-032: AWAITING_HUMAN_APPROVAL → ack_and_skip_approval."""
    guard = _guard()
    decision = guard.classify_stale_task(  # type: ignore[attr-defined]
        workflow_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        task_type=TaskType.REVIEW_SCENARIO,
    )
    assert decision.action == "ack_and_skip_approval"


def test_classify_stale_task_terminal_state() -> None:
    guard = _guard()
    decision = guard.classify_stale_task(  # type: ignore[attr-defined]
        workflow_state=WorkflowState.APPROVED,
        task_type=TaskType.COLLECT,
    )
    assert decision.action == "ack_and_skip_terminal"


def test_classify_stale_task_state_mismatch() -> None:
    guard = _guard()
    decision = guard.classify_stale_task(  # type: ignore[attr-defined]
        workflow_state=WorkflowState.REVIEWING,
        task_type=TaskType.COLLECT,
    )
    assert decision.action == "ack_and_skip"
    assert decision.reason == "state_mismatch"


def test_classify_stale_task_proceed_when_aligned() -> None:
    guard = _guard()
    decision = guard.classify_stale_task(  # type: ignore[attr-defined]
        workflow_state=WorkflowState.COLLECTING,
        task_type=TaskType.COLLECT,
    )
    assert decision.action == "proceed"


@pytest.mark.parametrize(
    ("task_type", "signal", "expected_post"),
    [
        (TaskType.COLLECT, TransitionSignal.STAGE_COMPLETED, WorkflowState.COLLECTED),
        (TaskType.SELECT_TOPIC, TransitionSignal.STAGE_COMPLETED, WorkflowState.TOPIC_SELECTED),
        (TaskType.SELECT_TOPIC, TransitionSignal.NO_SUITABLE_TOPIC, WorkflowState.NO_SUITABLE_TOPIC),
        (TaskType.GENERATE_SCENARIO, TransitionSignal.STAGE_COMPLETED, WorkflowState.SCENARIO_GENERATED),
        (TaskType.REVIEW_SCENARIO, TransitionSignal.CRITIC_PASS, WorkflowState.REVIEW_PASSED),
        (TaskType.REVIEW_SCENARIO, TransitionSignal.CRITIC_REVISE, WorkflowState.REVISION_REQUIRED),
        (TaskType.COLLECT, TransitionSignal.RETRIES_EXHAUSTED, WorkflowState.FAILED_PERMANENTLY),
        (TaskType.SELECT_TOPIC, TransitionSignal.UNRECOVERABLE_ERROR, WorkflowState.FAILED),
    ],
)
def test_post_transition_state_table(
    task_type: TaskType,
    signal: TransitionSignal,
    expected_post: WorkflowState,
) -> None:
    from worker.state_mapping import WorkflowStateGuard

    assert WorkflowStateGuard.post_transition_state(task_type, signal) == expected_post


def test_post_transition_state_unknown_pair_raises() -> None:
    from worker.state_mapping import WorkflowStateGuard

    with pytest.raises(Exception):
        WorkflowStateGuard.post_transition_state(TaskType.COLLECT, TransitionSignal.CRITIC_PASS)
