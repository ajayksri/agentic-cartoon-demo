"""Unit tests for WKR-001 persistence mappers (MOD-WKR-INV-034)."""

from __future__ import annotations

from datetime import UTC, datetime

from config.types import TaskType as ConfigTaskType
from persistence.types import PayloadReference, TaskRecord, TaskStatus, TaskType as PersTaskType
from workflow.types import WorkflowState

from worker.records import to_config_task_type, to_persistence_task_status, to_workflow_state

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _task_record(task_type: PersTaskType) -> TaskRecord:
    return TaskRecord(
        task_id="task-1",
        workflow_id="wf-1",
        task_type=task_type,
        attempt=1,
        status=TaskStatus.DISPATCHED,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def test_to_config_task_type_uses_value_equality() -> None:
    record = _task_record(PersTaskType.COLLECT)
    mapped = to_config_task_type(record)
    assert mapped == ConfigTaskType.COLLECT
    assert mapped.value == record.task_type.value


def test_to_workflow_state_maps_token() -> None:
    assert to_workflow_state("COLLECTED") == WorkflowState.COLLECTED
    assert to_workflow_state(WorkflowState.AWAITING_HUMAN_APPROVAL.value) == WorkflowState.AWAITING_HUMAN_APPROVAL


def test_to_persistence_task_status_identity() -> None:
    assert to_persistence_task_status(TaskStatus.DISPATCHED) == TaskStatus.DISPATCHED
    assert to_persistence_task_status(TaskStatus.COMPLETED) == TaskStatus.COMPLETED
