"""In-memory WorkflowEngine double for contract tests."""

from __future__ import annotations

from config.types import AppConfig
from workflow.types import (
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    ReconciliationResult,
    TransitionRequest,
    TransitionResult,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowStatus,
    WorkflowTimeline,
)


class FakeWorkflowEngine:
    """Configurable returns and exceptions per WorkflowEngine method."""

    def __init__(self) -> None:
        self._initiate_result: InitiateWorkflowResult | None = None
        self._initiate_error: Exception | None = None
        self._status_result: WorkflowStatus | None = None
        self._status_error: Exception | None = None
        self._history_result: WorkflowHistory | None = None
        self._history_error: Exception | None = None
        self._output_result: WorkflowOutput | None = None
        self._output_error: Exception | None = None
        self._approval_result: ApprovalActionResult | None = None
        self._approval_error: Exception | None = None
        self._timeline_result: WorkflowTimeline | None = None
        self._timeline_error: Exception | None = None
        self._call_count = 0

    def set_initiate_return(self, result: InitiateWorkflowResult) -> None:
        self._initiate_result = result
        self._initiate_error = None

    def set_status_return(self, status: WorkflowStatus) -> None:
        self._status_result = status
        self._status_error = None

    def set_history_return(self, history: WorkflowHistory) -> None:
        self._history_result = history
        self._history_error = None

    def set_output_return(self, output: WorkflowOutput) -> None:
        self._output_result = output
        self._output_error = None

    def set_approval_return(self, result: ApprovalActionResult) -> None:
        self._approval_result = result
        self._approval_error = None

    def set_timeline_return(self, timeline: WorkflowTimeline) -> None:
        self._timeline_result = timeline
        self._timeline_error = None

    def set_status_error(self, error: Exception) -> None:
        self._status_error = error

    def set_approval_error(self, error: Exception) -> None:
        self._approval_error = error

    def total_call_count(self) -> int:
        return self._call_count

    def initiate_workflow(
        self,
        *,
        config: AppConfig,
        request: InitiateWorkflowRequest | None = None,
    ) -> InitiateWorkflowResult:
        del config, request
        self._call_count += 1
        if self._initiate_error is not None:
            raise self._initiate_error
        if self._initiate_result is None:
            raise RuntimeError("FakeWorkflowEngine.initiate_workflow not configured")
        return self._initiate_result

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        del request
        self._call_count += 1
        raise NotImplementedError

    def apply_approval_action(
        self,
        *,
        workflow_id: str,
        action: ApprovalAction,
        actor: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalActionResult:
        del workflow_id, action, actor, idempotency_key
        self._call_count += 1
        if self._approval_error is not None:
            raise self._approval_error
        if self._approval_result is None:
            raise RuntimeError("FakeWorkflowEngine.apply_approval_action not configured")
        return self._approval_result

    def reconcile_stuck_workflows(
        self,
        *,
        config: AppConfig,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        del config, batch_size
        self._call_count += 1
        raise NotImplementedError

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        del workflow_id
        self._call_count += 1
        if self._status_error is not None:
            raise self._status_error
        if self._status_result is None:
            raise RuntimeError("FakeWorkflowEngine.get_workflow_status not configured")
        return self._status_result

    def get_workflow_history(self, workflow_id: str) -> WorkflowHistory:
        del workflow_id
        self._call_count += 1
        if self._history_error is not None:
            raise self._history_error
        if self._history_result is None:
            raise RuntimeError("FakeWorkflowEngine.get_workflow_history not configured")
        return self._history_result

    def get_workflow_output(self, workflow_id: str) -> WorkflowOutput:
        del workflow_id
        self._call_count += 1
        if self._output_error is not None:
            raise self._output_error
        if self._output_result is None:
            raise RuntimeError("FakeWorkflowEngine.get_workflow_output not configured")
        return self._output_result

    def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimeline:
        del workflow_id
        self._call_count += 1
        if self._timeline_error is not None:
            raise self._timeline_error
        if self._timeline_result is None:
            raise RuntimeError("FakeWorkflowEngine.get_workflow_timeline not configured")
        return self._timeline_result
