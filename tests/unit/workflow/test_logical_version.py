"""Pre-code test mold for WF-005 — LogicalVersionTracker (LLD §10)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config.types import TaskType

pytestmark = []

_WORKFLOW_ID = "wf-logical-version-001"


@pytest.fixture
def tracker() -> object:
    from workflow.outbox_builder import LogicalVersionTracker

    return LogicalVersionTracker()


@pytest.mark.parametrize("task_type", [TaskType.COLLECT, TaskType.SELECT_TOPIC])
def test_collect_and_select_topic_always_resolve_to_one(
    tracker: object,
    task_type: TaskType,
) -> None:
    """COLLECT and SELECT_TOPIC always use logical_version=1."""
    artifact_repo = MagicMock()

    version = tracker.resolve_for_task(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=task_type,
        artifact_repo=artifact_repo,
        increment=False,
    )

    assert version == 1
    artifact_repo.get_active_artifact.assert_not_called()


def test_generate_scenario_uses_active_scenario_logical_version(tracker: object) -> None:
    """GENERATE_SCENARIO resolves max(active_scenario.logical_version, 1)."""
    artifact_repo = MagicMock()
    scenario = MagicMock()
    scenario.logical_version = 3
    artifact_repo.get_active_artifact.return_value = scenario

    version = tracker.resolve_for_task(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.GENERATE_SCENARIO,
        artifact_repo=artifact_repo,
        increment=False,
    )

    assert version == 3


def test_generate_scenario_increment_bumps_version_before_build(tracker: object) -> None:
    """increment=True returns current logical_version + 1 for regeneration paths."""
    artifact_repo = MagicMock()
    scenario = MagicMock()
    scenario.logical_version = 2
    artifact_repo.get_active_artifact.return_value = scenario

    version = tracker.resolve_for_task(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.GENERATE_SCENARIO,
        artifact_repo=artifact_repo,
        increment=True,
    )

    assert version == 3


def test_review_scenario_matches_scenario_pass_without_increment(tracker: object) -> None:
    """REVIEW_SCENARIO uses active scenario version without increment at enqueue."""
    artifact_repo = MagicMock()
    scenario = MagicMock()
    scenario.logical_version = 2
    artifact_repo.get_active_artifact.return_value = scenario

    version = tracker.resolve_for_task(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.REVIEW_SCENARIO,
        artifact_repo=artifact_repo,
        increment=False,
    )

    assert version == 2


def test_missing_scenario_defaults_to_one(tracker: object) -> None:
    """When no active scenario exists, base resolves to max(0, 1) = 1."""
    artifact_repo = MagicMock()
    artifact_repo.get_active_artifact.return_value = None

    version = tracker.resolve_for_task(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.GENERATE_SCENARIO,
        artifact_repo=artifact_repo,
        increment=False,
    )

    assert version == 1
