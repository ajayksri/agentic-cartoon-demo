"""Unit tests for output renderer."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from api.types import WorkflowOutputResponse, WorkflowTimelineResponse, TimelineEventResponse
from cli.render import OutputRenderer
from workflow.types import WorkflowState


def test_render_output_excludes_package_values() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-1",
        state=WorkflowState.COLLECTED,
        package={"secret": "token"},
        is_complete=False,
    )
    out = io.StringIO()
    OutputRenderer().render_output(response, out=out)
    rendered = out.getvalue()
    assert "package_keys: secret" in rendered
    assert "token" not in rendered


def test_render_timeline_sorts_by_occurred_at() -> None:
    response = WorkflowTimelineResponse(
        workflow_id="wf-1",
        events=(
            TimelineEventResponse(
                occurred_at=datetime(2026, 8, 31, 12, 10, tzinfo=UTC),
                event_type="task",
                summary="second",
            ),
            TimelineEventResponse(
                occurred_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
                event_type="task",
                summary="first",
            ),
        ),
    )
    out = io.StringIO()
    OutputRenderer().render_timeline(response, out=out)
    rendered = out.getvalue()
    assert rendered.index("first") < rendered.index("second")
