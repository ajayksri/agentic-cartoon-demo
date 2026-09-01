"""Public workflow error types."""

from __future__ import annotations

from .types import ApprovalAction, TransitionSignal, WorkflowState


class WorkflowError(Exception):
    """Base class for all workflow module errors."""

    code: str = "WF_ERROR"


class WorkflowNotFoundError(WorkflowError):
    """Requested workflow does not exist."""

    code = "WF_NOT_FOUND"

    def __init__(self, message: str, *, workflow_id: str) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id


class WorkflowConflictError(WorkflowError):
    """Optimistic concurrency conflict or duplicate workflow identifier."""

    code = "WF_CONFLICT"

    def __init__(self, message: str, *, workflow_id: str) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id


class InvalidTransitionError(WorkflowError):
    """Transition signal is not valid for the current workflow state."""

    code = "WF_INVALID_TRANSITION"

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str,
        from_state: WorkflowState,
        signal: TransitionSignal,
    ) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.from_state = from_state
        self.signal = signal


class InvalidApprovalActionError(WorkflowError):
    """Approval action is not valid for the current workflow state."""

    code = "WF_INVALID_APPROVAL"

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str,
        action: ApprovalAction,
        current_state: WorkflowState,
    ) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.action = action
        self.current_state = current_state


class WorkflowTerminalError(WorkflowError):
    """Mutating operation attempted on a terminal workflow."""

    code = "WF_TERMINAL"

    def __init__(self, message: str, *, workflow_id: str, state: WorkflowState) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.state = state
