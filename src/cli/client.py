"""Default REST ApiClient implementation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from api.constants import (
    PATH_APPROVAL,
    PATH_HEALTH,
    PATH_HISTORY,
    PATH_INITIATE,
    PATH_OUTPUT,
    PATH_STATUS,
    PATH_TIMELINE,
)
from api.types import (
    ApiErrorEnvelope,
    ApprovalAction,
    HealthResponse,
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiRequest,
    SubmitApprovalApiResponse,
    TimelineEventResponse,
    TransitionRecordResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowState,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)
from observability import get_correlation_context
from observability.protocols import Logger, Tracer
from observability.types import TraceContext

from .constants import SPAN_HTTP_REQUEST
from .errors import CliApiError, map_api_error_envelope
from .transport import HttpTransport
from .types import CliClientConfig


class DefaultApiClient:
    """HTTP client for the api REST surface."""

    def __init__(
        self,
        *,
        config: CliClientConfig,
        transport: HttpTransport,
        logger: Logger,
        tracer: Tracer | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._logger = logger
        self._tracer = tracer

    @property
    def base_url(self) -> str:
        return self._config.api_base_url

    async def initiate_workflow(
        self,
        request: InitiateWorkflowApiRequest,
        *,
        trace_context: TraceContext | None = None,
    ) -> InitiateWorkflowApiResponse:
        _ = trace_context
        body = _initiate_request_to_json(request)
        response = await self._request("POST", PATH_INITIATE, json_body=body)
        return _parse_initiate_response(response)

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatusResponse:
        path = PATH_STATUS.format(workflow_id=workflow_id)
        response = await self._request("GET", path, workflow_id=workflow_id)
        return _parse_status_response(response)

    async def get_workflow_history(self, workflow_id: str) -> WorkflowHistoryResponse:
        path = PATH_HISTORY.format(workflow_id=workflow_id)
        response = await self._request("GET", path, workflow_id=workflow_id)
        return _parse_history_response(response)

    async def get_workflow_output(self, workflow_id: str) -> WorkflowOutputResponse:
        path = PATH_OUTPUT.format(workflow_id=workflow_id)
        response = await self._request("GET", path, workflow_id=workflow_id)
        return _parse_output_response(response)

    async def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimelineResponse:
        path = PATH_TIMELINE.format(workflow_id=workflow_id)
        response = await self._request("GET", path, workflow_id=workflow_id)
        return _parse_timeline_response(response)

    async def submit_approval(
        self,
        workflow_id: str,
        request: SubmitApprovalApiRequest,
    ) -> SubmitApprovalApiResponse:
        path = PATH_APPROVAL.format(workflow_id=workflow_id)
        action_value = getattr(request.action, "value", request.action)
        body = {"action": action_value}
        if request.actor is not None:
            body["actor"] = request.actor
        if request.idempotency_key is not None:
            body["idempotency_key"] = request.idempotency_key
        response = await self._request(
            "POST",
            path,
            json_body=body,
            workflow_id=workflow_id,
        )
        return _parse_approval_response(response)

    async def health_check(self) -> HealthResponse:
        response = await self._request("GET", PATH_HEALTH)
        data = _require_body(response)
        return HealthResponse(
            status=data["status"],  # type: ignore[arg-type]
            service_name=str(data["service_name"]),
            timestamp=_parse_datetime(str(data["timestamp"])),
        )

    async def close(self) -> None:
        await self._transport.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        span = None
        if self._tracer is not None:
            span = self._tracer.start_span(
                SPAN_HTTP_REQUEST,
                attributes={"method": method, "route": path},
            )
        carrier: dict[str, str] = {}
        get_correlation_context().inject(carrier)
        try:
            http_response = await self._transport.request(
                method,
                path,
                json_body=json_body,
                headers=carrier,
            )
            if http_response.status >= 400:
                body = http_response.body or {}
                envelope = ApiErrorEnvelope(
                    error_class=str(body.get("error_class", "API_INTERNAL")),
                    message=str(body.get("message", "API request failed")),
                    retryable=body.get("retryable"),
                    workflow_id=body.get("workflow_id") or workflow_id,
                    details=body.get("details"),
                )
                raise map_api_error_envelope(
                    envelope,
                    http_status=http_response.status,
                    workflow_id=workflow_id,
                )
            return _require_body(http_response.body)
        finally:
            if span is not None:
                span.end()


def create_api_client(*, config: CliClientConfig, logger: Logger) -> DefaultApiClient:
    """Default ApiClient factory (CG-CLI-009)."""
    timeout = config.request_timeout_seconds or 30.0
    transport = HttpTransport(
        base_url=config.api_base_url,
        timeout_seconds=timeout,
        logger=logger,
    )
    return DefaultApiClient(config=config, transport=transport, logger=logger)


def _initiate_request_to_json(request: InitiateWorkflowApiRequest) -> dict[str, object]:
    body: dict[str, object] = {}
    if request.workflow_id is not None:
        body["workflow_id"] = request.workflow_id
    if request.correlation_id is not None:
        body["correlation_id"] = request.correlation_id
    if request.actor is not None:
        body["actor"] = request.actor
    return body


def _require_body(body: dict[str, Any] | None) -> dict[str, Any]:
    if body is None:
        raise CliApiError("API response was empty")
    return body


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_state(value: object) -> WorkflowState:
    if isinstance(value, WorkflowState):
        return value
    return WorkflowState(str(value))


def _parse_action(value: object) -> ApprovalAction:
    if isinstance(value, ApprovalAction):
        return value
    return ApprovalAction(str(value))


def _parse_initiate_response(data: Mapping[str, Any]) -> InitiateWorkflowApiResponse:
    return InitiateWorkflowApiResponse(
        workflow_id=str(data["workflow_id"]),
        state=_parse_state(data["state"]),
        state_version=int(data["state_version"]),
        created_at=_parse_datetime(str(data["created_at"])),
        trace_id=data.get("trace_id"),
    )


def _parse_status_response(data: Mapping[str, Any]) -> WorkflowStatusResponse:
    return WorkflowStatusResponse(
        workflow_id=str(data["workflow_id"]),
        state=_parse_state(data["state"]),
        state_version=int(data["state_version"]),
        created_at=_parse_datetime(str(data["created_at"])),
        updated_at=_parse_datetime(str(data["updated_at"])),
        revision_count=int(data.get("revision_count", 0)),
        failure_reason=data.get("failure_reason"),
    )


def _parse_history_response(data: Mapping[str, Any]) -> WorkflowHistoryResponse:
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
    return WorkflowHistoryResponse(
        workflow_id=str(data["workflow_id"]),
        transitions=transitions,
    )


def _parse_output_response(data: Mapping[str, Any]) -> WorkflowOutputResponse:
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


def _parse_timeline_response(data: Mapping[str, Any]) -> WorkflowTimelineResponse:
    events = tuple(
        TimelineEventResponse(
            occurred_at=_parse_datetime(str(item["occurred_at"])),
            event_type=str(item["event_type"]),
            summary=str(item["summary"]),
            state=_parse_state(item["state"]) if item.get("state") else None,
            task_type=item.get("task_type"),
            attributes=item.get("attributes", {}),
        )
        for item in data.get("events", [])
    )
    return WorkflowTimelineResponse(
        workflow_id=str(data["workflow_id"]),
        events=events,
    )


def _parse_approval_response(data: Mapping[str, Any]) -> SubmitApprovalApiResponse:
    return SubmitApprovalApiResponse(
        workflow_id=str(data["workflow_id"]),
        action=_parse_action(data["action"]),
        from_state=_parse_state(data["from_state"]),
        to_state=_parse_state(data["to_state"]),
        state_version=int(data["state_version"]),
        transition_id=str(data["transition_id"]),
    )
