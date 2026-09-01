"""ApiClient backed by FastAPI TestClient (CLI → HTTP → API composition)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api import (
    PATH_HEALTH,
    PATH_WORKFLOW_APPROVAL,
    PATH_WORKFLOW_BY_ID,
    PATH_WORKFLOW_HISTORY,
    PATH_WORKFLOW_OUTPUT,
    PATH_WORKFLOW_TIMELINE,
    PATH_WORKFLOWS,
)
from api.types import (
    HealthResponse,
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiRequest,
    SubmitApprovalApiResponse,
    TimelineEventResponse,
    TransitionRecordResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)
from workflow.types import ApprovalAction, WorkflowState


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_state(value: object) -> WorkflowState:
    if isinstance(value, WorkflowState):
        return value
    return WorkflowState(str(value))


class AsgiApiClient:
    """cli.ApiClient protocol using an in-process TestClient (no real TCP)."""

    def __init__(self, test_client: Any, *, base_url: str = "http://testserver") -> None:
        self._client = test_client
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        return self._base_url

    async def initiate_workflow(
        self,
        request: InitiateWorkflowApiRequest,
        *,
        trace_context: object | None = None,
    ) -> InitiateWorkflowApiResponse:
        del trace_context
        body: dict[str, object] = {}
        if request.workflow_id is not None:
            body["workflow_id"] = request.workflow_id
        if request.correlation_id is not None:
            body["correlation_id"] = request.correlation_id
        if request.actor is not None:
            body["actor"] = request.actor
        response = self._client.post(PATH_WORKFLOWS, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"initiate failed: {response.status_code} {response.text}")
        data = response.json()
        return InitiateWorkflowApiResponse(
            workflow_id=str(data["workflow_id"]),
            state=_parse_state(data["state"]),
            state_version=int(data["state_version"]),
            created_at=_parse_datetime(str(data["created_at"])),
            trace_id=data.get("trace_id"),
        )

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatusResponse:
        path = PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id)
        response = self._client.get(path)
        if response.status_code >= 400:
            raise RuntimeError(f"status failed: {response.status_code} {response.text}")
        data = response.json()
        return WorkflowStatusResponse(
            workflow_id=str(data["workflow_id"]),
            state=_parse_state(data["state"]),
            state_version=int(data["state_version"]),
            created_at=_parse_datetime(str(data["created_at"])),
            updated_at=_parse_datetime(str(data["updated_at"])),
            revision_count=int(data.get("revision_count", 0)),
            failure_reason=data.get("failure_reason"),
        )

    async def get_workflow_history(self, workflow_id: str) -> WorkflowHistoryResponse:
        path = PATH_WORKFLOW_HISTORY.format(workflow_id=workflow_id)
        response = self._client.get(path)
        data = response.json()
        transitions = tuple(
            TransitionRecordResponse(
                transition_id=str(item["transition_id"]),
                from_state=_parse_state(item["from_state"]),
                to_state=_parse_state(item["to_state"]),
                reason=str(item["reason"]),
                occurred_at=_parse_datetime(str(item["occurred_at"])),
                actor=item.get("actor"),
            )
            for item in data.get("transitions", [])
        )
        return WorkflowHistoryResponse(workflow_id=str(data["workflow_id"]), transitions=transitions)

    async def get_workflow_output(self, workflow_id: str) -> WorkflowOutputResponse:
        path = PATH_WORKFLOW_OUTPUT.format(workflow_id=workflow_id)
        response = self._client.get(path)
        data = response.json()
        package = data.get("package", {})
        if not isinstance(package, dict):
            package = {}
        return WorkflowOutputResponse(
            workflow_id=str(data["workflow_id"]),
            state=_parse_state(data["state"]),
            package=package,
            is_complete=bool(data.get("is_complete", False)),
            failure_reason=data.get("failure_reason"),
        )

    async def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimelineResponse:
        path = PATH_WORKFLOW_TIMELINE.format(workflow_id=workflow_id)
        response = self._client.get(path)
        data = response.json()
        events = tuple(
            TimelineEventResponse(
                occurred_at=_parse_datetime(str(item["occurred_at"])),
                event_type=str(item["event_type"]),
                summary=str(item["summary"]),
                state=_parse_state(item["state"]) if item.get("state") else None,
                task_type=item.get("task_type"),
                attributes=dict(item.get("attributes") or {}),
            )
            for item in data.get("events", [])
        )
        return WorkflowTimelineResponse(workflow_id=str(data["workflow_id"]), events=events)

    async def submit_approval(
        self,
        workflow_id: str,
        request: SubmitApprovalApiRequest,
    ) -> SubmitApprovalApiResponse:
        path = PATH_WORKFLOW_APPROVAL.format(workflow_id=workflow_id)
        body: dict[str, object] = {"action": request.action.value}
        if request.actor is not None:
            body["actor"] = request.actor
        if request.idempotency_key is not None:
            body["idempotency_key"] = request.idempotency_key
        response = self._client.post(path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"approval failed: {response.status_code} {response.text}")
        data = response.json()
        return SubmitApprovalApiResponse(
            workflow_id=str(data["workflow_id"]),
            action=ApprovalAction(str(data["action"])),
            from_state=_parse_state(data["from_state"]),
            to_state=_parse_state(data["to_state"]),
            state_version=int(data["state_version"]),
            transition_id=str(data["transition_id"]),
        )

    async def health_check(self) -> HealthResponse:
        response = self._client.get(PATH_HEALTH)
        data = response.json()
        from api.types import HealthStatus

        return HealthResponse(
            status=HealthStatus(str(data["status"])),
            service_name=str(data.get("service_name", "cartoon-demo-api")),
            timestamp=_parse_datetime(str(data["timestamp"])),
        )

    async def close(self) -> None:
        """No-op close for TestClient-backed client (cli.DefaultCliApp teardown)."""
        return None
