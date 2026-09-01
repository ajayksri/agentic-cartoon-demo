"""Workflow state guard and stale-task classification (LLD §4.9)."""

# GUARDRAIL: Workflow — stale or out-of-order tasks are skipped, not blindly executed.

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config.types import TaskType
from workflow.types import TransitionSignal, WorkflowState


@dataclass(frozen=True, slots=True)
class StaleTaskDecision:
    action: Literal[
        "proceed",
        "ack_and_skip",
        "ack_and_skip_approval",
        "ack_and_skip_terminal",
    ]
    reason: str | None = None


_POST_TRANSITION_TABLE: dict[tuple[TaskType, TransitionSignal], WorkflowState] = {
    (TaskType.COLLECT, TransitionSignal.STAGE_COMPLETED): WorkflowState.COLLECTED,
    (TaskType.SELECT_TOPIC, TransitionSignal.STAGE_COMPLETED): WorkflowState.TOPIC_SELECTED,
    (TaskType.SELECT_TOPIC, TransitionSignal.NO_SUITABLE_TOPIC): WorkflowState.NO_SUITABLE_TOPIC,
    (TaskType.GENERATE_SCENARIO, TransitionSignal.STAGE_COMPLETED): WorkflowState.SCENARIO_GENERATED,
    (TaskType.REVIEW_SCENARIO, TransitionSignal.CRITIC_PASS): WorkflowState.REVIEW_PASSED,
    (TaskType.REVIEW_SCENARIO, TransitionSignal.CRITIC_REVISE): WorkflowState.REVISION_REQUIRED,
}

_EXHAUSTED_SIGNALS = (
    TransitionSignal.RETRIES_EXHAUSTED,
    TransitionSignal.UNRECOVERABLE_ERROR,
)


class WorkflowStateGuard:
    """Stale-task classification and transition state tables."""

    TERMINAL_STATES: frozenset[WorkflowState] = frozenset(
        {
            WorkflowState.NO_SUITABLE_TOPIC,
            WorkflowState.APPROVED,
            WorkflowState.REJECTED,
            WorkflowState.REVIEW_FAILED,
            WorkflowState.FAILED,
            WorkflowState.FAILED_PERMANENTLY,
        }
    )

    def classify_stale_task(
        self,
        *,
        workflow_state: WorkflowState,
        task_type: TaskType,
    ) -> StaleTaskDecision:
        if workflow_state == WorkflowState.AWAITING_HUMAN_APPROVAL:
            return StaleTaskDecision(action="ack_and_skip_approval")
        if workflow_state in self.TERMINAL_STATES:
            return StaleTaskDecision(action="ack_and_skip_terminal")
        expected = self.expected_state_for_task(task_type)
        if workflow_state != expected:
            return StaleTaskDecision(action="ack_and_skip", reason="state_mismatch")
        return StaleTaskDecision(action="proceed")

    @staticmethod
    def expected_state_for_task(task_type: TaskType) -> WorkflowState:
        mapping = {
            TaskType.COLLECT: WorkflowState.COLLECTING,
            TaskType.SELECT_TOPIC: WorkflowState.SELECTING_TOPIC,
            TaskType.GENERATE_SCENARIO: WorkflowState.GENERATING_SCENARIO,
            TaskType.REVIEW_SCENARIO: WorkflowState.REVIEWING,
        }
        return mapping[task_type]

    @staticmethod
    def post_transition_state(
        task_type: TaskType,
        signal: TransitionSignal,
    ) -> WorkflowState:
        if signal in _EXHAUSTED_SIGNALS:
            if signal == TransitionSignal.RETRIES_EXHAUSTED:
                return WorkflowState.FAILED_PERMANENTLY
            return WorkflowState.FAILED
        key = (task_type, signal)
        post_state = _POST_TRANSITION_TABLE.get(key)
        if post_state is None:
            raise ValueError(
                f"Unknown post-transition pair: task_type={task_type.value}, signal={signal.value}"
            )
        return post_state
