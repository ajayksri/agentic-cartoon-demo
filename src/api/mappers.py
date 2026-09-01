"""Pure mapping helpers from workflow domain types to REST DTOs."""

from __future__ import annotations

from workflow.types import (
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    TimelineEvent,
    TransitionRecord,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowStatus,
    WorkflowTimeline,
)

from .types import (
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiResponse,
    TimelineEventResponse,
    TransitionRecordResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)


def map_to_initiate_request(
    api_request: InitiateWorkflowApiRequest,
) -> InitiateWorkflowRequest:
    """Map REST initiate body to workflow.InitiateWorkflowRequest."""
    return InitiateWorkflowRequest(
        workflow_id=api_request.workflow_id,
        correlation_id=api_request.correlation_id,
        actor=api_request.actor,
    )


def map_transition_record(record: TransitionRecord) -> TransitionRecordResponse:
    return TransitionRecordResponse(
        transition_id=record.transition_id,
        from_state=record.from_state,
        to_state=record.to_state,
        reason=record.reason,
        occurred_at=record.occurred_at,
        actor=record.actor,
    )


def map_workflow_status(status: WorkflowStatus) -> WorkflowStatusResponse:
    return WorkflowStatusResponse(
        workflow_id=status.workflow_id,
        state=status.state,
        state_version=status.state_version,
        created_at=status.created_at,
        updated_at=status.updated_at,
        revision_count=status.revision_count,
        failure_reason=status.failure_reason,
    )


def map_workflow_history(history: WorkflowHistory) -> WorkflowHistoryResponse:
    return WorkflowHistoryResponse(
        workflow_id=history.workflow_id,
        transitions=tuple(map_transition_record(t) for t in history.transitions),
    )


def map_workflow_output(output: WorkflowOutput) -> WorkflowOutputResponse:
    return WorkflowOutputResponse(
        workflow_id=output.workflow_id,
        state=output.state,
        package=output.package,
        is_complete=output.is_complete,
        failure_reason=output.failure_reason,
    )


def map_timeline_event(event: TimelineEvent) -> TimelineEventResponse:
    return TimelineEventResponse(
        occurred_at=event.occurred_at,
        event_type=event.event_type,
        summary=event.summary,
        state=event.state,
        task_type=event.task_type,
        attributes=event.attributes,
    )


def map_workflow_timeline(timeline: WorkflowTimeline) -> WorkflowTimelineResponse:
    sorted_events = sorted(timeline.events, key=lambda event: event.occurred_at)
    return WorkflowTimelineResponse(
        workflow_id=timeline.workflow_id,
        events=tuple(map_timeline_event(e) for e in sorted_events),
    )


def map_initiate_result(
    result: InitiateWorkflowResult,
    *,
    trace_id: str | None = None,
) -> InitiateWorkflowApiResponse:
    return InitiateWorkflowApiResponse(
        workflow_id=result.workflow_id,
        state=result.state,
        state_version=result.state_version,
        created_at=result.transition.occurred_at,
        trace_id=trace_id,
    )


def map_approval_result(result: ApprovalActionResult) -> SubmitApprovalApiResponse:
    return SubmitApprovalApiResponse(
        workflow_id=result.workflow_id,
        action=result.action,
        from_state=result.from_state,
        to_state=result.to_state,
        state_version=result.state_version,
        transition_id=result.transition_id,
    )
