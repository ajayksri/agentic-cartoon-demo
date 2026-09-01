"""Pre-code test mold for WF-008 — ReconciliationScanner predicates (LLD §7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from config.types import BackoffConfig, RetryPolicy, TaskType
from persistence.types import TaskStatus
from workflow import WorkflowState

pytestmark = []

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
_STUCK_THRESHOLD_SECONDS = 60.0
_WORKFLOW_ID = "wf-reconcile-test-001"


def _workflow_record(
    *,
    state: WorkflowState = WorkflowState.COLLECTED,
    updated_at: datetime | None = None,
) -> MagicMock:
    record = MagicMock()
    record.workflow_id = _WORKFLOW_ID
    record.state = MagicMock(value=state.value)
    record.state_version = 1
    record.updated_at = updated_at or (_FIXED_NOW - timedelta(seconds=_STUCK_THRESHOLD_SECONDS + 30))
    return record


def _task_record(*, status: TaskStatus = TaskStatus.PENDING, attempt: int = 1) -> MagicMock:
    task = MagicMock()
    task.task_id = "task-001"
    task.task_type = MagicMock(value=TaskType.SELECT_TOPIC.value)
    task.status = status
    task.attempt = attempt
    task.created_at = _FIXED_NOW
    return task


@pytest.fixture
def scanner() -> object:
    from workflow.reconcile import ReconciliationScanner

    return ReconciliationScanner(
        config=MagicMock(),
        workflow_repo=MagicMock(),
        outbox_repo=MagicMock(),
        artifact_repo=MagicMock(),
        executor=MagicMock(),
        outbox_builder=MagicMock(),
        transition_table=MagicMock(),
        engine=MagicMock(),
        transaction_guard=MagicMock(),
        transaction_manager=MagicMock(),
        clock=lambda: _FIXED_NOW,
        stuck_threshold_overrides={WorkflowState.COLLECTING: _STUCK_THRESHOLD_SECONDS},
    )


def test_rp001_expected_task_for_collected_state(scanner: object) -> None:
    """RP-001: COLLECTED expects SELECT_TOPIC outbox when missing."""
    scanner._transition_table.expected_outbox_task.return_value = TaskType.SELECT_TOPIC  # type: ignore[attr-defined]

    expected = scanner._rp001_expected_task(  # type: ignore[attr-defined]
        workflow=_workflow_record(state=WorkflowState.COLLECTED),
        tasks=(),
        unpublished=(),
    )

    assert expected == TaskType.SELECT_TOPIC


def test_rp001_generating_scenario_returns_none_when_task_in_flight(scanner: object) -> None:
    """GENERATING_SCENARIO regeneration: in-flight GENERATE_SCENARIO task → no RP-001."""
    scanner._transition_table.expected_outbox_task.return_value = None  # type: ignore[attr-defined]
    in_flight = _task_record(status=TaskStatus.IN_PROGRESS)
    in_flight.task_type = MagicMock(value=TaskType.GENERATE_SCENARIO.value)

    expected = scanner._rp001_expected_task(  # type: ignore[attr-defined]
        workflow=_workflow_record(state=WorkflowState.GENERATING_SCENARIO),
        tasks=(in_flight,),
        unpublished=(),
    )

    assert expected is None


def test_rp001_generating_scenario_returns_generate_when_terminal_and_no_outbox(
    scanner: object,
) -> None:
    """GENERATING_SCENARIO regeneration path expects GENERATE_SCENARIO when task terminal."""
    scanner._transition_table.expected_outbox_task.return_value = None  # type: ignore[attr-defined]
    terminal = _task_record(status=TaskStatus.FAILED)
    terminal.task_type = MagicMock(value=TaskType.GENERATE_SCENARIO.value)

    expected = scanner._rp001_expected_task(  # type: ignore[attr-defined]
        workflow=_workflow_record(state=WorkflowState.GENERATING_SCENARIO),
        tasks=(terminal,),
        unpublished=(),
    )

    assert expected == TaskType.GENERATE_SCENARIO


@pytest.mark.parametrize(
    ("attempt", "max_attempts", "expected_retriable"),
    [
        (0, 3, True),
        (2, 3, True),
        (3, 3, False),
        (4, 3, False),
    ],
)
def test_is_stuck_retriable_boundary_at_max_attempts(
    scanner: object,
    attempt: int,
    max_attempts: int,
    expected_retriable: bool,
) -> None:
    """is_stuck_retriable compares attempt to max_attempts only (LLD §7.4)."""
    latest_task = _task_record(attempt=attempt) if attempt > 0 else None
    retry_policy = RetryPolicy(
        max_attempts=max_attempts,
        backoff=BackoffConfig(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0),
    )

    result = scanner.is_stuck_retriable(  # type: ignore[attr-defined]
        latest_task=latest_task,
        retry_policy=retry_policy,
    )

    assert result is expected_retriable


@pytest.mark.parametrize(
    ("status", "expected_stuck", "expected_in_flight"),
    [
        (TaskStatus.PENDING, False, True),
        (TaskStatus.DISPATCHED, False, True),
        (TaskStatus.IN_PROGRESS, False, True),
        (TaskStatus.FAILED, True, False),
        (TaskStatus.COMPLETED, True, False),
    ],
)
def test_rp003_in_flight_exclusion_by_latest_task_status(
    scanner: object,
    status: TaskStatus,
    expected_stuck: bool,
    expected_in_flight: bool,
) -> None:
    """RP-003: in-flight latest task statuses are not stuck; terminal tasks may be."""
    evaluation = scanner._evaluate_rp003(  # type: ignore[attr-defined]
        workflow=_workflow_record(state=WorkflowState.COLLECTING),
        latest_task=_task_record(status=status),
    )

    assert evaluation.is_stuck is expected_stuck
    assert evaluation.in_flight_task is expected_in_flight
    assert evaluation.threshold_seconds == _STUCK_THRESHOLD_SECONDS
    assert evaluation.elapsed_seconds > evaluation.threshold_seconds


def test_dedupe_priority_rp003_over_rp001(scanner: object) -> None:
    """De-dupe by workflow_id: RP-003 beats RP-001 (LLD §7.2)."""
    from workflow.reconcile import ReconciliationCandidate

    rp003 = ReconciliationCandidate(
        workflow=_workflow_record(),
        pattern_id="RP-003",
        expected_task_type=TaskType.COLLECT,
    )
    rp001 = ReconciliationCandidate(
        workflow=_workflow_record(),
        pattern_id="RP-001",
        expected_task_type=TaskType.SELECT_TOPIC,
    )

    deduped = scanner._dedupe_candidates([rp001, rp003])  # type: ignore[attr-defined]

    assert len(deduped) == 1
    assert deduped[0].pattern_id == "RP-003"


def test_collect_candidates_detects_rp004_via_fetch_unpublished(scanner: object) -> None:
    """RP-004: terminal workflow with unpublished outbox via fetch_unpublished supplement."""
    from persistence.types import OutboxEntry, OutboxStatus, WorkflowState as PersistenceWorkflowState
    from workflow.reconcile import ReconciliationCandidate

    terminal_workflow = _workflow_record(state=WorkflowState.APPROVED)
    terminal_workflow.state = MagicMock(value=WorkflowState.APPROVED.value)

    scanner._workflow_repo.list_workflows_for_reconciliation.return_value = []  # type: ignore[attr-defined]
    scanner._workflow_repo.get_workflow.return_value = terminal_workflow  # type: ignore[attr-defined]
    pending_entry = MagicMock(
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.COLLECT,
        status=OutboxStatus.PENDING,
    )
    scanner._outbox_repo.fetch_unpublished.return_value = [pending_entry]  # type: ignore[attr-defined]

    candidates = scanner.collect_candidates(batch_size=10)  # type: ignore[attr-defined]

    assert len(candidates) == 1
    assert candidates[0].pattern_id == "RP-004"
