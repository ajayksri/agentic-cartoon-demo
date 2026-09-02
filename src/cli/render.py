"""Human-readable stdout formatting for CLI subcommand responses."""

from __future__ import annotations

import sys
from enum import StrEnum
from typing import TextIO

from api.types import (
    InitiateWorkflowApiResponse,
    SubmitApprovalApiResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)

from .approval_review import build_approval_review, format_approval_review


class OutputFormat(StrEnum):
    TEXT = "text"


class OutputRenderer:
    """Plain-text stdout renderer for V1 CLI subcommands."""

    def render_initiate(
        self,
        response: InitiateWorkflowApiResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        sink.write(f"workflow_id: {response.workflow_id}\n")
        sink.write(f"state: {response.state.value}\n")

    def render_status(
        self,
        response: WorkflowStatusResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        sink.write(f"workflow_id: {response.workflow_id}\n")
        sink.write(f"state: {response.state.value}\n")
        sink.write(f"state_version: {response.state_version}\n")
        sink.write(f"created_at: {response.created_at.isoformat()}\n")
        sink.write(f"updated_at: {response.updated_at.isoformat()}\n")

    def render_history(
        self,
        response: WorkflowHistoryResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        for transition in response.transitions:
            sink.write(
                f"{transition.occurred_at.isoformat()} "
                f"{transition.from_state.value} -> {transition.to_state.value}\n"
            )

    def render_output(
        self,
        response: WorkflowOutputResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        review = build_approval_review(response)
        sink.write(format_approval_review(review))

    def render_timeline(
        self,
        response: WorkflowTimelineResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        sorted_events = sorted(response.events, key=lambda event: event.occurred_at)
        for event in sorted_events:
            sink.write(
                f"{event.occurred_at.isoformat()} [{event.event_type}] {event.summary}\n"
            )

    def render_approve(
        self,
        response: SubmitApprovalApiResponse,
        *,
        out: TextIO | None = None,
    ) -> None:
        sink = out or sys.stdout
        sink.write(f"to_state: {response.to_state.value}\n")
        sink.write(f"state_version: {response.state_version}\n")
