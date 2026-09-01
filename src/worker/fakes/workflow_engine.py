"""Fake workflow engine spy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from workflow.constants import TRANSIENT_STATES
from workflow.transition_table import _PRIMARY_MATRIX
from workflow.types import (
    TransitionRecord,
    TransitionRequest,
    TransitionResult,
    TransitionSignal,
    WorkflowState,
)

_ERROR_TO_STATE: dict[TransitionSignal, WorkflowState] = {
    TransitionSignal.UNRECOVERABLE_ERROR: WorkflowState.FAILED,
    TransitionSignal.RETRIES_EXHAUSTED: WorkflowState.FAILED_PERMANENTLY,
}


@dataclass
class FakeWorkflowEngine:
    """Records apply_transition calls and returns contract-shaped TransitionResult."""

    transitions: list[TransitionRequest] = field(default_factory=list)

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        self.transitions.append(request)
        row = _PRIMARY_MATRIX.get((request.expected_state, request.signal))
        if row is not None:
            to_state = row.to_state
        elif (
            request.signal in _ERROR_TO_STATE
            and request.expected_state in TRANSIENT_STATES
        ):
            to_state = _ERROR_TO_STATE[request.signal]
        else:
            to_state = request.expected_state

        now = datetime.now(UTC)
        transition_id = f"tr-{len(self.transitions)}"
        transition = TransitionRecord(
            transition_id=transition_id,
            workflow_id=request.workflow_id,
            from_state=request.expected_state,
            to_state=to_state,
            reason=request.reason,
            occurred_at=now,
            actor=request.actor,
        )
        return TransitionResult(
            workflow_id=request.workflow_id,
            from_state=request.expected_state,
            to_state=to_state,
            state_version=len(self.transitions),
            transition_id=transition_id,
            transition=transition,
            outbox_written=False,
            enqueued_task=None,
        )
