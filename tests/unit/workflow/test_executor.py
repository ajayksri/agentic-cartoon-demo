"""Pre-code test mold for WF-007 — TransitionExecutor (LLD §5)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.types import TaskType
from persistence.errors import PersistenceConflictError, PersistenceNotFoundError
from workflow import WorkflowConflictError, WorkflowNotFoundError, TransitionSignal, WorkflowState

pytestmark = []

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
_WORKFLOW_ID = "wf-executor-test-001"


def _workflow_record(*, state_version: int = 1, revision_count: int = 0) -> MagicMock:
    record = MagicMock()
    record.workflow_id = _WORKFLOW_ID
    record.state_version = state_version
    record.revision_count = revision_count
    record.state = MagicMock(value=WorkflowState.COLLECTING.value)
    return record


def _transition_decision(*, increment_revision_count: bool = False) -> MagicMock:
    decision = MagicMock()
    decision.to_state = WorkflowState.COLLECTED
    decision.set_failure_reason = None
    decision.increment_revision_count = increment_revision_count
    return decision


def _transition_record() -> MagicMock:
    return MagicMock(
        transition_id="tr-001",
        workflow_id=_WORKFLOW_ID,
        from_state=MagicMock(value=WorkflowState.COLLECTING.value),
        to_state=MagicMock(value=WorkflowState.COLLECTED.value),
        reason="stage_completed",
        occurred_at=_FIXED_NOW,
        actor=None,
    )


def _outbox_build_result() -> MagicMock:
    result = MagicMock()
    result.payload_json = {}
    result.task_record = MagicMock()
    result.outbox_insert = MagicMock()
    result.task_spec = MagicMock(task_type=TaskType.SELECT_TOPIC)
    return result


@pytest.fixture
def fake_repos() -> tuple[MagicMock, MagicMock]:
    workflow_repo = MagicMock()
    workflow_repo.update_workflow_state.return_value = _workflow_record(state_version=2)
    workflow_repo.append_transition.return_value = _transition_record()
    workflow_repo.create_task.return_value = MagicMock()
    outbox_repo = MagicMock()
    return workflow_repo, outbox_repo


@pytest.fixture
def executor(fake_repos: tuple[MagicMock, MagicMock]) -> object:
    from workflow.executor import TransitionExecutor

    workflow_repo, outbox_repo = fake_repos
    guard = MagicMock()
    return TransitionExecutor(
        workflow_repo=workflow_repo,
        outbox_repo=outbox_repo,
        transaction_guard=guard,
    )


def test_execute_transition_persistence_write_order(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """MOD-WF-INV-006: update_workflow_state → append_transition → create_task → outbox.insert."""
    workflow_repo, outbox_repo = fake_repos
    call_log: list[str] = []

    def log_update(*args: object, **kwargs: object) -> MagicMock:
        call_log.append("update_workflow_state")
        return _workflow_record(state_version=2)

    def log_append(*args: object, **kwargs: object) -> MagicMock:
        call_log.append("append_transition")
        return _transition_record()

    def log_create(*args: object, **kwargs: object) -> MagicMock:
        call_log.append("create_task")
        return MagicMock()

    def log_insert(*args: object, **kwargs: object) -> MagicMock:
        call_log.append("outbox.insert")
        return MagicMock()

    workflow_repo.update_workflow_state.side_effect = log_update
    workflow_repo.append_transition.side_effect = log_append
    workflow_repo.create_task.side_effect = log_create
    outbox_repo.insert.side_effect = log_insert

    executor.execute_transition(  # type: ignore[attr-defined]
        workflow=_workflow_record(),
        decision=_transition_decision(),
        transition=_transition_record(),
        outbox=_outbox_build_result(),
    )

    assert call_log == [
        "update_workflow_state",
        "append_transition",
        "create_task",
        "outbox.insert",
    ]


def test_execute_transition_passes_revision_count_kwarg(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """Critic revise path passes optional revision_count to update_workflow_state."""
    workflow_repo, _ = fake_repos
    decision = _transition_decision(increment_revision_count=True)

    executor.execute_transition(  # type: ignore[attr-defined]
        workflow=_workflow_record(revision_count=1),
        decision=decision,
        transition=_transition_record(),
        outbox=None,
        revision_count=2,
    )

    workflow_repo.update_workflow_state.assert_called_once()
    assert workflow_repo.update_workflow_state.call_args.kwargs["revision_count"] == 2


def test_execute_transition_passes_failure_reason_kwarg(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """Wildcard failure persists set_failure_reason via update_workflow_state."""
    workflow_repo, _ = fake_repos
    decision = _transition_decision()
    decision.to_state = WorkflowState.FAILED
    decision.set_failure_reason = "worker_error"

    executor.execute_transition(  # type: ignore[attr-defined]
        workflow=_workflow_record(),
        decision=decision,
        transition=_transition_record(),
        outbox=None,
    )

    assert (
        workflow_repo.update_workflow_state.call_args.kwargs["failure_reason"]
        == "worker_error"
    )


def test_persistence_conflict_maps_to_workflow_conflict(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """PersistenceConflictError → WorkflowConflictError."""
    workflow_repo, _ = fake_repos
    workflow_repo.update_workflow_state.side_effect = PersistenceConflictError(
        "version mismatch",
    )

    with pytest.raises(WorkflowConflictError) as exc_info:
        executor.execute_transition(  # type: ignore[attr-defined]
            workflow=_workflow_record(),
            decision=_transition_decision(),
            transition=_transition_record(),
            outbox=None,
        )

    assert exc_info.value.workflow_id == _WORKFLOW_ID


def test_persistence_not_found_maps_to_workflow_not_found(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """PersistenceNotFoundError → WorkflowNotFoundError."""
    workflow_repo, _ = fake_repos
    workflow_repo.update_workflow_state.side_effect = PersistenceNotFoundError(
        "missing",
    )

    with pytest.raises(WorkflowNotFoundError) as exc_info:
        executor.execute_transition(  # type: ignore[attr-defined]
            workflow=_workflow_record(),
            decision=_transition_decision(),
            transition=_transition_record(),
            outbox=None,
        )

    assert exc_info.value.workflow_id == _WORKFLOW_ID


def test_recreate_expected_outbox_does_not_update_state_or_append_transition(
    executor: object,
    fake_repos: tuple[MagicMock, MagicMock],
) -> None:
    """RP-001 path: create_task + outbox.insert only (LLD §5.3)."""
    workflow_repo, outbox_repo = fake_repos
    outbox_builder = MagicMock()
    outbox_builder.build.return_value = _outbox_build_result()
    artifact_repo = MagicMock()

    executor.recreate_expected_outbox(  # type: ignore[attr-defined]
        workflow=_workflow_record(),
        expected_task_type=TaskType.SELECT_TOPIC,
        artifact_repo=artifact_repo,
        outbox_builder=outbox_builder,
    )

    workflow_repo.update_workflow_state.assert_not_called()
    workflow_repo.append_transition.assert_not_called()
    workflow_repo.create_task.assert_called_once()
    outbox_repo.insert.assert_called_once()
