"""Fake ApiClient for contract and unit tests."""

from __future__ import annotations

from typing import Any

from api.types import (
    HealthResponse,
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiRequest,
    SubmitApprovalApiResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)
from observability.types import TraceContext


class FakeApiClient:
    """Configurable in-memory ApiClient double."""

    def __init__(self) -> None:
        self.base_url_value = "http://test"
        self.initiate_return: InitiateWorkflowApiResponse | None = None
        self.status_return: WorkflowStatusResponse | None = None
        self.history_return: WorkflowHistoryResponse | None = None
        self.output_return: WorkflowOutputResponse | None = None
        self.timeline_return: WorkflowTimelineResponse | None = None
        self.approval_return: SubmitApprovalApiResponse | None = None
        self.health_return: HealthResponse | None = None
        self.status_error: Exception | None = None
        self.approval_error: Exception | None = None
        self.connection_error: Exception | None = None
        self.initiate_calls: list[InitiateWorkflowApiRequest] = []
        self.get_workflow_status_calls: list[str] = []
        self.get_workflow_history_calls: list[str] = []
        self.get_workflow_output_calls: list[str] = []
        self.get_workflow_timeline_calls: list[str] = []
        self.submit_approval_calls: list[tuple[str, str]] = []
        self.health_check_calls: int = 0

    @property
    def base_url(self) -> str:
        return self.base_url_value

    def set_initiate_return(self, response: InitiateWorkflowApiResponse) -> None:
        self.initiate_return = response

    def set_status_return(self, response: WorkflowStatusResponse) -> None:
        self.status_return = response

    def set_history_return(self, response: WorkflowHistoryResponse) -> None:
        self.history_return = response

    def set_output_return(self, response: WorkflowOutputResponse) -> None:
        self.output_return = response

    def set_timeline_return(self, response: WorkflowTimelineResponse) -> None:
        self.timeline_return = response

    def set_approval_return(self, response: SubmitApprovalApiResponse) -> None:
        self.approval_return = response

    def set_status_error(self, error: Exception) -> None:
        self.status_error = error

    def set_approval_error(self, error: Exception) -> None:
        self.approval_error = error

    def set_connection_error(self, error: Exception) -> None:
        self.connection_error = error

    def total_call_count(self) -> int:
        return (
            len(self.initiate_calls)
            + len(self.get_workflow_status_calls)
            + len(self.get_workflow_history_calls)
            + len(self.get_workflow_output_calls)
            + len(self.get_workflow_timeline_calls)
            + len(self.submit_approval_calls)
            + self.health_check_calls
        )

    async def initiate_workflow(
        self,
        request: InitiateWorkflowApiRequest,
        *,
        trace_context: TraceContext | None = None,
    ) -> InitiateWorkflowApiResponse:
        _ = trace_context
        self._maybe_raise_connection()
        self.initiate_calls.append(request)
        if self.initiate_return is None:
            raise RuntimeError("initiate_return not configured")
        return self.initiate_return

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatusResponse:
        self._maybe_raise_connection()
        self.get_workflow_status_calls.append(workflow_id)
        if self.status_error is not None:
            raise self.status_error
        if self.status_return is None:
            raise RuntimeError("status_return not configured")
        return self.status_return

    async def get_workflow_history(self, workflow_id: str) -> WorkflowHistoryResponse:
        self._maybe_raise_connection()
        self.get_workflow_history_calls.append(workflow_id)
        if self.history_return is None:
            raise RuntimeError("history_return not configured")
        return self.history_return

    async def get_workflow_output(self, workflow_id: str) -> WorkflowOutputResponse:
        self._maybe_raise_connection()
        self.get_workflow_output_calls.append(workflow_id)
        if self.output_return is None:
            raise RuntimeError("output_return not configured")
        return self.output_return

    async def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimelineResponse:
        self._maybe_raise_connection()
        self.get_workflow_timeline_calls.append(workflow_id)
        if self.timeline_return is None:
            raise RuntimeError("timeline_return not configured")
        return self.timeline_return

    async def submit_approval(
        self,
        workflow_id: str,
        request: SubmitApprovalApiRequest,
    ) -> SubmitApprovalApiResponse:
        self._maybe_raise_connection()
        action_value = getattr(request.action, "value", request.action)
        self.submit_approval_calls.append((workflow_id, str(action_value)))
        if self.approval_error is not None:
            raise self.approval_error
        if self.approval_return is None:
            raise RuntimeError("approval_return not configured")
        return self.approval_return

    async def health_check(self) -> HealthResponse:
        self._maybe_raise_connection()
        self.health_check_calls += 1
        if self.health_return is None:
            raise RuntimeError("health_return not configured")
        return self.health_return

    async def close(self) -> None:
        return None

    def _maybe_raise_connection(self) -> None:
        if self.connection_error is not None:
            raise self.connection_error
