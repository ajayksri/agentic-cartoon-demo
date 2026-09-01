"""Pre-code test mold for WKR-006 — Scenario C post-state helper (LLD §4.9, §8.6)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from workflow.types import TransitionSignal, WorkflowState


def test_scenario_c_skip_when_current_equals_expected_post() -> None:
    """WKR-TC-016 helper: deterministic equality — skip transition when states match."""
    from worker.state_mapping import WorkflowStateGuard

    expected_post = WorkflowStateGuard.post_transition_state(
        TaskType.GENERATE_SCENARIO,
        TransitionSignal.STAGE_COMPLETED,
    )
    current = WorkflowState.SCENARIO_GENERATED
    assert current == expected_post
    assert expected_post == WorkflowState.SCENARIO_GENERATED


def test_scenario_c_no_ordinal_comparison() -> None:
    """LLD §8.6: equality only — REVIEW_PASSED must not compare ordinally to REVIEWING."""
    from worker.state_mapping import WorkflowStateGuard

    expected_post = WorkflowStateGuard.post_transition_state(
        TaskType.REVIEW_SCENARIO,
        TransitionSignal.CRITIC_PASS,
    )
    mismatch = WorkflowState.REVIEWING
    assert mismatch != expected_post


def test_scenario_c_loser_expected_post_from_table() -> None:
    """Pure table test for Scenario C loser reload compare."""
    from worker.state_mapping import WorkflowStateGuard

    for task_type, signal in (
        (TaskType.COLLECT, TransitionSignal.STAGE_COMPLETED),
        (TaskType.SELECT_TOPIC, TransitionSignal.STAGE_COMPLETED),
        (TaskType.GENERATE_SCENARIO, TransitionSignal.STAGE_COMPLETED),
        (TaskType.REVIEW_SCENARIO, TransitionSignal.CRITIC_REVISE),
    ):
        post = WorkflowStateGuard.post_transition_state(task_type, signal)
        assert isinstance(post, WorkflowState)
