"""Pre-code test mold for WF-004 — TransitionTable (LLD §3)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from workflow import (
    ApprovalAction,
    TERMINAL_WORKFLOW_STATES,
    TransitionSignal,
    WorkflowState,
)

pytestmark = []


_PRIMARY_MATRIX_CASES = [
    pytest.param(
        WorkflowState.COLLECTING,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.COLLECTED,
        TaskType.SELECT_TOPIC,
        False,
        False,
        None,
        id="collecting_stage_completed",
    ),
    pytest.param(
        WorkflowState.COLLECTED,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.SELECTING_TOPIC,
        None,
        False,
        False,
        None,
        id="collected_stage_completed",
    ),
    pytest.param(
        WorkflowState.SELECTING_TOPIC,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.TOPIC_SELECTED,
        TaskType.GENERATE_SCENARIO,
        False,
        False,
        None,
        id="selecting_topic_stage_completed",
    ),
    pytest.param(
        WorkflowState.SELECTING_TOPIC,
        TransitionSignal.NO_SUITABLE_TOPIC,
        WorkflowState.NO_SUITABLE_TOPIC,
        None,
        False,
        False,
        None,
        id="selecting_topic_no_suitable_topic",
    ),
    pytest.param(
        WorkflowState.TOPIC_SELECTED,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.GENERATING_SCENARIO,
        None,
        False,
        False,
        None,
        id="topic_selected_stage_completed",
    ),
    pytest.param(
        WorkflowState.GENERATING_SCENARIO,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.SCENARIO_GENERATED,
        TaskType.REVIEW_SCENARIO,
        False,
        False,
        None,
        id="generating_scenario_stage_completed",
    ),
    pytest.param(
        WorkflowState.SCENARIO_GENERATED,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.REVIEWING,
        None,
        False,
        False,
        None,
        id="scenario_generated_stage_completed",
    ),
    pytest.param(
        WorkflowState.REVIEWING,
        TransitionSignal.CRITIC_PASS,
        WorkflowState.REVIEW_PASSED,
        None,
        False,
        False,
        None,
        id="reviewing_critic_pass",
    ),
    pytest.param(
        WorkflowState.REVISION_REQUIRED,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.GENERATING_SCENARIO,
        TaskType.GENERATE_SCENARIO,
        False,
        True,
        None,
        id="revision_required_stage_completed",
    ),
    pytest.param(
        WorkflowState.REVIEW_PASSED,
        TransitionSignal.STAGE_COMPLETED,
        WorkflowState.AWAITING_HUMAN_APPROVAL,
        None,
        False,
        False,
        None,
        id="review_passed_stage_completed",
    ),
]

_TRANSIENT_NON_PAUSE_STATES = [
    state
    for state in WorkflowState
    if state not in TERMINAL_WORKFLOW_STATES and state != WorkflowState.AWAITING_HUMAN_APPROVAL
]

_EXPECTED_OUTBOX_TASK_CASES = [
    (WorkflowState.COLLECTING, TaskType.COLLECT),
    (WorkflowState.COLLECTED, TaskType.SELECT_TOPIC),
    (WorkflowState.SELECTING_TOPIC, None),
    (WorkflowState.TOPIC_SELECTED, TaskType.GENERATE_SCENARIO),
    (WorkflowState.GENERATING_SCENARIO, None),
    (WorkflowState.SCENARIO_GENERATED, TaskType.REVIEW_SCENARIO),
    (WorkflowState.REVISION_REQUIRED, None),
    (WorkflowState.AWAITING_HUMAN_APPROVAL, None),
    (WorkflowState.APPROVED, None),
]


@pytest.fixture
def transition_table() -> object:
    from workflow.transition_table import TransitionTable

    return TransitionTable()


@pytest.mark.parametrize(
    (
        "from_state",
        "signal",
        "expected_to_state",
        "expected_outbox",
        "increment_revision_count",
        "increment_logical_version",
        "set_failure_reason",
    ),
    _PRIMARY_MATRIX_CASES,
)
def test_primary_matrix_lookup(
    transition_table: object,
    from_state: WorkflowState,
    signal: TransitionSignal,
    expected_to_state: WorkflowState,
    expected_outbox: TaskType | None,
    increment_revision_count: bool,
    increment_logical_version: bool,
    set_failure_reason: str | None,
) -> None:
    """LLD §3.2 primary matrix rows resolve to expected TransitionDecision."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=from_state,
        signal=signal,
        revision_count=0,
        max_scenario_revisions=2,
    )

    assert decision.from_state == from_state
    assert decision.to_state == expected_to_state
    assert decision.signal == signal
    assert decision.outbox_task_type == expected_outbox
    assert decision.increment_revision_count is increment_revision_count
    assert decision.increment_logical_version is increment_logical_version
    assert decision.set_failure_reason == set_failure_reason


def test_critic_revise_under_revision_limit_increments_count(transition_table: object) -> None:
    """REVIEWING + CRITIC_REVISE below max → REVISION_REQUIRED with revision increment."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=WorkflowState.REVIEWING,
        signal=TransitionSignal.CRITIC_REVISE,
        revision_count=0,
        max_scenario_revisions=2,
    )

    assert decision.to_state == WorkflowState.REVISION_REQUIRED
    assert decision.increment_revision_count is True
    assert decision.set_failure_reason is None


def test_critic_revise_at_revision_limit_routes_to_review_failed(transition_table: object) -> None:
    """REVIEWING + CRITIC_REVISE at max → REVIEW_FAILED (WF-TC-017 matrix)."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=WorkflowState.REVIEWING,
        signal=TransitionSignal.CRITIC_REVISE,
        revision_count=2,
        max_scenario_revisions=2,
    )

    assert decision.to_state == WorkflowState.REVIEW_FAILED
    assert decision.set_failure_reason == "max_scenario_revisions_exceeded"
    assert decision.increment_revision_count is False


@pytest.mark.parametrize("terminal_state", sorted(TERMINAL_WORKFLOW_STATES, key=str))
def test_terminal_state_rejects_any_signal(
    transition_table: object,
    terminal_state: WorkflowState,
) -> None:
    """Terminal states reject all TransitionSignal values."""
    from workflow import InvalidTransitionError

    with pytest.raises(InvalidTransitionError):
        transition_table.lookup(  # type: ignore[attr-defined]
            current_state=terminal_state,
            signal=TransitionSignal.STAGE_COMPLETED,
            revision_count=0,
            max_scenario_revisions=2,
        )


def test_pause_state_rejects_transition_signals(transition_table: object) -> None:
    """AWAITING_HUMAN_APPROVAL rejects any TransitionSignal (pause guard)."""
    from workflow import InvalidTransitionError

    with pytest.raises(InvalidTransitionError):
        transition_table.lookup(  # type: ignore[attr-defined]
            current_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
            signal=TransitionSignal.STAGE_COMPLETED,
            revision_count=0,
            max_scenario_revisions=2,
        )


@pytest.mark.parametrize("transient_state", _TRANSIENT_NON_PAUSE_STATES)
def test_unrecoverable_error_wildcard_to_failed(
    transition_table: object,
    transient_state: WorkflowState,
) -> None:
    """Wildcard UNRECOVERABLE_ERROR on transient non-pause states → FAILED."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=transient_state,
        signal=TransitionSignal.UNRECOVERABLE_ERROR,
        revision_count=0,
        max_scenario_revisions=2,
    )

    assert decision.to_state == WorkflowState.FAILED
    assert decision.outbox_task_type is None


@pytest.mark.parametrize("transient_state", _TRANSIENT_NON_PAUSE_STATES)
def test_retries_exhausted_wildcard_to_failed_permanently(
    transition_table: object,
    transient_state: WorkflowState,
) -> None:
    """Wildcard RETRIES_EXHAUSTED on transient non-pause states → FAILED_PERMANENTLY."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=transient_state,
        signal=TransitionSignal.RETRIES_EXHAUSTED,
        revision_count=0,
        max_scenario_revisions=2,
    )

    assert decision.to_state == WorkflowState.FAILED_PERMANENTLY
    assert decision.outbox_task_type is None


@pytest.mark.parametrize("transient_state", _TRANSIENT_NON_PAUSE_STATES)
def test_reconciliation_repair_row_to_failed(
    transition_table: object,
    transient_state: WorkflowState,
) -> None:
    """Scanner-only RECONCILIATION_REPAIR row → FAILED with stuck_state_timeout."""
    decision = transition_table.lookup(  # type: ignore[attr-defined]
        current_state=transient_state,
        signal=TransitionSignal.RECONCILIATION_REPAIR,
        revision_count=0,
        max_scenario_revisions=2,
    )

    assert decision.to_state == WorkflowState.FAILED
    assert decision.set_failure_reason == "stuck_state_timeout"
    assert decision.outbox_task_type is None


def test_created_stage_completed_not_in_primary_matrix(transition_table: object) -> None:
    """CREATED + STAGE_COMPLETED MUST NOT exist — initiate path is engine-only."""
    from workflow import InvalidTransitionError

    with pytest.raises(InvalidTransitionError):
        transition_table.lookup(  # type: ignore[attr-defined]
            current_state=WorkflowState.CREATED,
            signal=TransitionSignal.STAGE_COMPLETED,
            revision_count=0,
            max_scenario_revisions=2,
        )


@pytest.mark.parametrize(
    ("action", "expected_to_state", "expected_outbox", "increment_logical_version"),
    [
        (ApprovalAction.APPROVE, WorkflowState.APPROVED, None, False),
        (ApprovalAction.REJECT, WorkflowState.REJECTED, None, False),
        (
            ApprovalAction.REQUEST_REGENERATION,
            WorkflowState.GENERATING_SCENARIO,
            TaskType.GENERATE_SCENARIO,
            True,
        ),
    ],
)
def test_lookup_approval_matrix(
    transition_table: object,
    action: ApprovalAction,
    expected_to_state: WorkflowState,
    expected_outbox: TaskType | None,
    increment_logical_version: bool,
) -> None:
    """LLD §3.5 approval action matrix."""
    decision = transition_table.lookup_approval(action=action)  # type: ignore[attr-defined]

    assert decision.action == action
    assert decision.from_state == WorkflowState.AWAITING_HUMAN_APPROVAL
    assert decision.to_state == expected_to_state
    assert decision.outbox_task_type == expected_outbox
    assert decision.increment_logical_version is increment_logical_version


@pytest.mark.parametrize(("state", "expected_task"), _EXPECTED_OUTBOX_TASK_CASES)
def test_expected_outbox_task_state_table(
    transition_table: object,
    state: WorkflowState,
    expected_task: TaskType | None,
) -> None:
    """expected_outbox_task returns RP-001 expectations per LLD §3.1."""
    assert transition_table.expected_outbox_task(state) == expected_task  # type: ignore[attr-defined]


def test_is_terminal_and_is_pause_helpers(transition_table: object) -> None:
    """Classification helpers align with terminal and pause sets."""
    for state in TERMINAL_WORKFLOW_STATES:
        assert transition_table.is_terminal(state) is True  # type: ignore[attr-defined]
        assert transition_table.is_pause(state) is False  # type: ignore[attr-defined]

    assert transition_table.is_pause(WorkflowState.AWAITING_HUMAN_APPROVAL) is True  # type: ignore[attr-defined]
    assert transition_table.is_terminal(WorkflowState.COLLECTING) is False  # type: ignore[attr-defined]
