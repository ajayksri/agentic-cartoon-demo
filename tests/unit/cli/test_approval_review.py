"""Unit tests for approval review projection."""

from __future__ import annotations

import io

from api.types import WorkflowOutputResponse, WorkflowTimelineResponse, TimelineEventResponse
from cli.approval_review import build_approval_review, format_approval_review
from cli.render import OutputRenderer
from workflow.types import WorkflowState


def _sample_package() -> dict[str, object]:
    return {
        "source": {
            "story_count": 25,
            "content": {"stories": [{"title": "secret story", "api_key": "hidden"}]},
        },
        "topic": {
            "selected_topic": "Rust async patterns",
            "why_interesting": "Timely and humorous",
            "content": {"selected_topic": "ignored nested blob"},
        },
        "scenario": {
            "artifact_id": "art-scenario-2",
            "logical_version": 2,
            "premise": "Two developers argue about async runtime choices",
            "characters": ["Alice", "Bob"],
            "panels": [
                {"caption": "Office desk", "dialogue": "Async is too hard!"},
                {"caption": "Office desk", "dialogue": "Just use await everywhere!"},
            ],
            "punchline": "They both ship blocking I/O anyway.",
            "content": {"premise": "should not print raw content blob"},
        },
        "critic": {
            "status": "PASS",
            "issues": [],
            "content": {"status": "PASS"},
        },
        "execution": {
            "invocations": [{"agent_name": "scenario_generator", "provider": "fake"}],
        },
        "secret": "token",
    }


def test_build_approval_review_extracts_review_fields() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-1",
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        package=_sample_package(),
        is_complete=False,
    )

    review = build_approval_review(response)

    assert review.workflow_id == "wf-1"
    assert review.topic_selected == "Rust async patterns"
    assert review.topic_rationale == "Timely and humorous"
    assert review.scenario_artifact_id == "art-scenario-2"
    assert review.scenario_logical_version == 2
    assert review.premise == "Two developers argue about async runtime choices"
    assert review.characters == ("Alice", "Bob")
    assert len(review.panels) == 2
    assert review.panels[0].dialogue == "Async is too hard!"
    assert review.punchline == "They both ship blocking I/O anyway."
    assert review.critic_verdict == "PASS"
    assert review.critic_issues == ()


def test_format_approval_review_shows_scenario_and_excludes_source() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-1",
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        package=_sample_package(),
        is_complete=False,
    )

    rendered = format_approval_review(build_approval_review(response))

    assert "workflow_id: wf-1" in rendered
    assert "scenario_logical_version: 2" in rendered
    assert "selected_topic: Rust async patterns" in rendered
    assert "premise: Two developers argue about async runtime choices" in rendered
    assert "panel 1:" in rendered
    assert "dialogue: Async is too hard!" in rendered
    assert "punchline: They both ship blocking I/O anyway." in rendered
    assert "verdict: PASS" in rendered
    assert "issues:" not in rendered
    assert "secret story" not in rendered
    assert "api_key" not in rendered
    assert "hidden" not in rendered
    assert "token" not in rendered
    assert "raw content blob" not in rendered
    assert "invocations" not in rendered


def test_build_approval_review_maps_persisted_artifact_field_names() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-live",
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        package={
            "topic": {
                "selected_topic": "Rust async patterns",
                "rationale": "",
                "why_interesting": "Because async debates are funny",
            },
            "scenario": {
                "artifact_id": "art-1",
                "logical_version": 1,
                "premise": "Two developers argue",
                "characters": [{"name": "Alice", "role": "character"}],
                "panels": [{"caption": "Office desk", "dialogue": "Async is too hard!"}],
                "punchline": "They ship blocking I/O anyway.",
            },
            "critic": {"verdict": "", "status": "PASS", "issues": []},
        },
        is_complete=False,
    )

    review = build_approval_review(response)

    assert review.topic_rationale == "Because async debates are funny"
    assert review.panels[0].scene == "Office desk"
    assert review.critic_verdict == "PASS"


def test_build_approval_review_formats_critic_issues_when_dimensions_empty() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-revise",
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        package={
            "critic": {
                "status": "REVISE",
                "dimensions": {},
                "issues": [
                    {
                        "dimension": "humor",
                        "description": "Punchline is too subtle",
                    }
                ],
            },
        },
        is_complete=False,
    )

    review = build_approval_review(response)

    assert review.critic_verdict == "REVISE"
    assert review.critic_issues == (("humor", "Punchline is too subtle"),)


def test_format_approval_review_shows_critic_issues_on_revise() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-revise",
        state=WorkflowState.REVISION_REQUIRED,
        package={
            "critic": {
                "status": "REVISE",
                "issues": [
                    {
                        "dimension": "humor",
                        "description": "Punchline is too subtle",
                    }
                ],
            },
        },
        is_complete=False,
    )

    rendered = format_approval_review(build_approval_review(response))

    assert "verdict: REVISE" in rendered
    assert "issues:" in rendered
    assert "humor: Punchline is too subtle" in rendered


def test_format_approval_review_handles_missing_sections() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-early",
        state=WorkflowState.COLLECTING,
        package={},
        is_complete=False,
    )

    rendered = format_approval_review(build_approval_review(response))

    assert "selected_topic: (not available yet)" in rendered
    assert "premise: (not available yet)" in rendered
    assert "panels: (not available yet)" in rendered
    assert "verdict: (not available yet)" in rendered


def test_render_output_uses_approval_review() -> None:
    response = WorkflowOutputResponse(
        workflow_id="wf-1",
        state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        package=_sample_package(),
        is_complete=False,
    )
    out = io.StringIO()
    OutputRenderer().render_output(response, out=out)
    rendered = out.getvalue()

    assert "selected_topic: Rust async patterns" in rendered
    assert "package_keys" not in rendered
    assert "state:" not in rendered


def test_render_timeline_sorts_by_occurred_at() -> None:
    from datetime import UTC, datetime

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
