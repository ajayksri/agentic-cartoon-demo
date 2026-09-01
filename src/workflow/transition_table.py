"""Pure transition matrix lookup (LLD §3)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Durable human-in-the-loop pause — AWAITING_HUMAN_APPROVAL
# is a persisted workflow state with no active worker lease, surviving process restarts.
# GUARDRAIL: Workflow — only legal state transitions; revision cap → REVIEW_FAILED terminal.

from __future__ import annotations

from dataclasses import dataclass

from config.types import TaskType

from .constants import PAUSE_STATES, TERMINAL_STATES, TRANSIENT_STATES
from .errors import InvalidTransitionError
from .types import ApprovalAction, TransitionSignal, WorkflowState


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    """Pure outcome of TransitionTable lookup; no I/O."""

    from_state: WorkflowState
    to_state: WorkflowState
    signal: TransitionSignal
    outbox_task_type: TaskType | None = None
    increment_revision_count: bool = False
    increment_logical_version: bool = False
    set_failure_reason: str | None = None
    append_transition: bool = True


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Parallel to TransitionDecision for apply_approval_action path."""

    action: ApprovalAction
    from_state: WorkflowState
    to_state: WorkflowState
    outbox_task_type: TaskType | None = None
    increment_logical_version: bool = False


@dataclass(frozen=True, slots=True)
class _RowSpec:
    to_state: WorkflowState
    outbox_task_type: TaskType | None = None
    increment_revision_count: bool = False
    increment_logical_version: bool = False
    set_failure_reason: str | None = None


_PRIMARY_MATRIX: dict[tuple[WorkflowState, TransitionSignal], _RowSpec] = {
    (WorkflowState.COLLECTING, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.COLLECTED, TaskType.SELECT_TOPIC
    ),
    (WorkflowState.COLLECTED, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.SELECTING_TOPIC
    ),
    (WorkflowState.SELECTING_TOPIC, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.TOPIC_SELECTED, TaskType.GENERATE_SCENARIO
    ),
    (WorkflowState.SELECTING_TOPIC, TransitionSignal.NO_SUITABLE_TOPIC): _RowSpec(
        WorkflowState.NO_SUITABLE_TOPIC
    ),
    (WorkflowState.TOPIC_SELECTED, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.GENERATING_SCENARIO
    ),
    (WorkflowState.GENERATING_SCENARIO, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.SCENARIO_GENERATED, TaskType.REVIEW_SCENARIO
    ),
    (WorkflowState.SCENARIO_GENERATED, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.REVIEWING
    ),
    (WorkflowState.REVIEWING, TransitionSignal.CRITIC_PASS): _RowSpec(
        WorkflowState.REVIEW_PASSED
    ),
    (WorkflowState.REVISION_REQUIRED, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.GENERATING_SCENARIO,
        TaskType.GENERATE_SCENARIO,
        increment_logical_version=True,
    ),
    (WorkflowState.REVIEW_PASSED, TransitionSignal.STAGE_COMPLETED): _RowSpec(
        WorkflowState.AWAITING_HUMAN_APPROVAL
    ),
}

_EXPECTED_OUTBOX_BY_STATE: dict[WorkflowState, TaskType | None] = {
    WorkflowState.COLLECTING: TaskType.COLLECT,
    WorkflowState.COLLECTED: TaskType.SELECT_TOPIC,
    WorkflowState.SELECTING_TOPIC: None,
    WorkflowState.TOPIC_SELECTED: TaskType.GENERATE_SCENARIO,
    WorkflowState.GENERATING_SCENARIO: None,
    WorkflowState.SCENARIO_GENERATED: TaskType.REVIEW_SCENARIO,
    WorkflowState.REVISION_REQUIRED: None,
    WorkflowState.AWAITING_HUMAN_APPROVAL: None,
    WorkflowState.APPROVED: None,
}

_APPROVAL_MATRIX: dict[ApprovalAction, _RowSpec] = {
    ApprovalAction.APPROVE: _RowSpec(WorkflowState.APPROVED),
    ApprovalAction.REJECT: _RowSpec(WorkflowState.REJECTED),
    ApprovalAction.REQUEST_REGENERATION: _RowSpec(
        WorkflowState.GENERATING_SCENARIO,
        TaskType.GENERATE_SCENARIO,
        increment_logical_version=True,
    ),
}


class TransitionTable:
    """Pure (state, signal) → TransitionDecision registry."""

    def lookup(
        self,
        *,
        current_state: WorkflowState,
        signal: TransitionSignal,
        revision_count: int,
        max_scenario_revisions: int,
    ) -> TransitionDecision:
        if current_state in TERMINAL_STATES:
            raise InvalidTransitionError(
                f"Cannot transition from terminal state {current_state.value}",
                workflow_id="",
                from_state=current_state,
                signal=signal,
            )
        if current_state in PAUSE_STATES:
            raise InvalidTransitionError(
                f"Cannot apply transition signal in pause state {current_state.value}",
                workflow_id="",
                from_state=current_state,
                signal=signal,
            )

        if (
            current_state == WorkflowState.REVIEWING
            and signal == TransitionSignal.CRITIC_REVISE
        ):
            if revision_count >= max_scenario_revisions:
                return TransitionDecision(
                    from_state=current_state,
                    to_state=WorkflowState.REVIEW_FAILED,
                    signal=signal,
                    set_failure_reason="max_scenario_revisions_exceeded",
                )
            return TransitionDecision(
                from_state=current_state,
                to_state=WorkflowState.REVISION_REQUIRED,
                signal=signal,
                increment_revision_count=True,
            )

        row = _PRIMARY_MATRIX.get((current_state, signal))
        if row is not None:
            return TransitionDecision(
                from_state=current_state,
                to_state=row.to_state,
                signal=signal,
                outbox_task_type=row.outbox_task_type,
                increment_revision_count=row.increment_revision_count,
                increment_logical_version=row.increment_logical_version,
                set_failure_reason=row.set_failure_reason,
            )

        if signal == TransitionSignal.UNRECOVERABLE_ERROR and current_state in TRANSIENT_STATES:
            return TransitionDecision(
                from_state=current_state,
                to_state=WorkflowState.FAILED,
                signal=signal,
            )

        if signal == TransitionSignal.RETRIES_EXHAUSTED and current_state in TRANSIENT_STATES:
            return TransitionDecision(
                from_state=current_state,
                to_state=WorkflowState.FAILED_PERMANENTLY,
                signal=signal,
            )

        if (
            signal == TransitionSignal.RECONCILIATION_REPAIR
            and current_state in TRANSIENT_STATES
        ):
            return TransitionDecision(
                from_state=current_state,
                to_state=WorkflowState.FAILED,
                signal=signal,
                set_failure_reason="stuck_state_timeout",
            )

        raise InvalidTransitionError(
            f"Invalid transition {current_state.value} + {signal.value}",
            workflow_id="",
            from_state=current_state,
            signal=signal,
        )

    def lookup_approval(self, *, action: ApprovalAction) -> ApprovalDecision:
        row = _APPROVAL_MATRIX[action]
        return ApprovalDecision(
            action=action,
            from_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
            to_state=row.to_state,
            outbox_task_type=row.outbox_task_type,
            increment_logical_version=row.increment_logical_version,
        )

    def is_terminal(self, state: WorkflowState) -> bool:
        return state in TERMINAL_STATES

    def is_pause(self, state: WorkflowState) -> bool:
        return state in PAUSE_STATES

    def expected_outbox_task(self, state: WorkflowState) -> TaskType | None:
        return _EXPECTED_OUTBOX_BY_STATE.get(state)
