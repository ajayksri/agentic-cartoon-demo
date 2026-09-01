"""Unit tests for DefaultApiClient JSON response parsing."""

from __future__ import annotations

from datetime import UTC, datetime

from workflow.types import ApprovalAction, WorkflowState

from cli.client import (
    _parse_approval_response,
    _parse_history_response,
    _parse_initiate_response,
    _parse_output_response,
    _parse_status_response,
    _parse_timeline_response,
)

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def test_parse_initiate_response_coerces_state_string() -> None:
    response = _parse_initiate_response(
        {
            "workflow_id": "wf-001",
            "state": "COLLECTING",
            "state_version": 1,
            "created_at": "2026-08-31T12:00:00+00:00",
            "trace_id": "trace-1",
        }
    )
    assert response.workflow_id == "wf-001"
    assert response.state == WorkflowState.COLLECTING
    assert response.state_version == 1
    assert response.trace_id == "trace-1"


def test_parse_status_response_coerces_state_string() -> None:
    response = _parse_status_response(
        {
            "workflow_id": "wf-001",
            "state": "AWAITING_HUMAN_APPROVAL",
            "state_version": 7,
            "created_at": "2026-08-31T12:00:00+00:00",
            "updated_at": "2026-08-31T12:05:00+00:00",
            "revision_count": 1,
        }
    )
    assert response.state == WorkflowState.AWAITING_HUMAN_APPROVAL
    assert response.revision_count == 1


def test_parse_history_response_coerces_transition_states() -> None:
    response = _parse_history_response(
        {
            "workflow_id": "wf-001",
            "transitions": [
                {
                    "transition_id": "t-1",
                    "from_state": "CREATED",
                    "to_state": "COLLECTING",
                    "reason": "workflow_initiated",
                    "occurred_at": "2026-08-31T12:00:00+00:00",
                    "actor": "operator",
                }
            ],
        }
    )
    assert len(response.transitions) == 1
    transition = response.transitions[0]
    assert transition.from_state == WorkflowState.CREATED
    assert transition.to_state == WorkflowState.COLLECTING
    assert transition.actor == "operator"


def test_parse_output_response_coerces_state_string() -> None:
    response = _parse_output_response(
        {
            "workflow_id": "wf-001",
            "state": "AWAITING_HUMAN_APPROVAL",
            "package": {"topic_selection": {}, "scenario": {}, "critic": {}},
            "is_complete": False,
        }
    )
    assert response.state == WorkflowState.AWAITING_HUMAN_APPROVAL
    assert set(response.package.keys()) == {"topic_selection", "scenario", "critic"}


def test_parse_timeline_response_coerces_optional_state() -> None:
    response = _parse_timeline_response(
        {
            "workflow_id": "wf-001",
            "events": [
                {
                    "occurred_at": "2026-08-31T12:00:00+00:00",
                    "event_type": "state_change",
                    "summary": "entered collecting",
                    "state": "COLLECTING",
                },
                {
                    "occurred_at": "2026-08-31T12:01:00+00:00",
                    "event_type": "note",
                    "summary": "no state",
                },
            ],
        }
    )
    assert len(response.events) == 2
    assert response.events[0].state == WorkflowState.COLLECTING
    assert response.events[1].state is None


def test_parse_approval_response_coerces_action_and_states() -> None:
    response = _parse_approval_response(
        {
            "workflow_id": "wf-001",
            "action": "APPROVE",
            "from_state": "AWAITING_HUMAN_APPROVAL",
            "to_state": "APPROVED",
            "state_version": 8,
            "transition_id": "t-approve",
        }
    )
    assert response.action == ApprovalAction.APPROVE
    assert response.from_state == WorkflowState.AWAITING_HUMAN_APPROVAL
    assert response.to_state == WorkflowState.APPROVED
