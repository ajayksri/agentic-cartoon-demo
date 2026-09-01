"""Unit tests for RT-007 — OutboxMessageBuilder (LLD §11.1)."""

from __future__ import annotations

from datetime import UTC, datetime

from persistence.types import OutboxEntry, OutboxStatus, PayloadReference, TaskRecord, TaskStatus
from persistence.types import TaskType as PersTaskType

from runtime.outbox import OutboxMessageBuilder

_WORKFLOW_ID = "wf-outbox-1"
_TASK_ID = "task-outbox-1"


def _sample_entry(*, ref_id: str = "pl-42") -> OutboxEntry:
    return OutboxEntry(
        outbox_id="ob-1",
        workflow_id=_WORKFLOW_ID,
        task_id=_TASK_ID,
        task_type=PersTaskType.COLLECT,
        payload_reference=PayloadReference(ref_id=ref_id, ref_kind="payload"),
        idempotency_key="idem-1",
        status=OutboxStatus.PENDING,
        created_at=datetime.now(UTC),
    )


def test_builder_maps_payload_ref_id_to_string() -> None:
    """LLD §11.1: payload_reference.ref_id mapped to TaskMessage payload_reference string."""
    builder = OutboxMessageBuilder(workflow_repo=_FakeWorkflowRepo())

    message = builder.build(_sample_entry())

    assert message.payload_reference == "pl-42"


def test_builder_loads_task_via_workflow_repo_get_task() -> None:
    """LLD §11.1: builder calls workflow_repo.get_task for attempt mapping."""
    repo = _FakeWorkflowRepo()
    builder = OutboxMessageBuilder(workflow_repo=repo)

    builder.build(_sample_entry(ref_id="pl-1"))

    assert repo.get_task_calls == [_TASK_ID]


class _FakeWorkflowRepo:
    def __init__(self) -> None:
        self.get_task_calls: list[str] = []

    def get_task(self, task_id: str) -> TaskRecord | None:
        self.get_task_calls.append(task_id)
        return TaskRecord(
            task_id=task_id,
            workflow_id=_WORKFLOW_ID,
            task_type=PersTaskType.COLLECT,
            status=TaskStatus.PENDING,
            attempt=1,
            payload_reference=PayloadReference(ref_id="pl-1", ref_kind="payload"),
            idempotency_key="idem-1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
