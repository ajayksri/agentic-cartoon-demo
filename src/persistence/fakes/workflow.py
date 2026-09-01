"""In-memory workflow repository fake."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import UTC, datetime

from persistence.constants import TASK_PAYLOAD_REF_KIND
from persistence.errors import (
    PersistenceConflictError,
    PersistenceDuplicateError,
    PersistenceNotFoundError,
    PersistenceTransactionError,
    PersistenceValidationError,
)
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import (
    JsonValue,
    PayloadReference,
    TaskRecord,
    TaskStatus,
    WorkflowRecord,
    WorkflowState,
    WorkflowTransitionRecord,
)


class InMemoryWorkflowRepo:
    """Dict-backed workflow repository for tests."""

    def __init__(
        self,
        *,
        transaction_manager: InMemoryTransactionManager | None = None,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._workflows: dict[str, WorkflowRecord] = {}
        self._transitions: list[WorkflowTransitionRecord] = []
        self._tasks: dict[str, TaskRecord] = {}
        self._payloads: dict[str, JsonValue] = {}
        if transaction_manager is not None:
            transaction_manager.register_store(self._snapshot, self._restore)

    def _snapshot(self) -> dict[str, object]:
        return {
            "workflows": copy.deepcopy(self._workflows),
            "transitions": copy.deepcopy(self._transitions),
            "tasks": copy.deepcopy(self._tasks),
            "payloads": copy.deepcopy(self._payloads),
        }

    def _restore(self, snapshot: dict[str, object]) -> None:
        self._workflows = snapshot["workflows"]  # type: ignore[assignment]
        self._transitions = snapshot["transitions"]  # type: ignore[assignment]
        self._tasks = snapshot["tasks"]  # type: ignore[assignment]
        self._payloads = snapshot["payloads"]  # type: ignore[assignment]

    def _require_active_transaction(self, operation: str) -> None:
        if (
            self._transaction_manager is None
            or not self._transaction_manager.is_in_transaction()
        ):
            raise PersistenceTransactionError(
                f"Operation {operation} requires an active transaction"
            )

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        return self._workflows.get(workflow_id)

    def create_workflow(
        self,
        workflow_id: str,
        *,
        initial_state: WorkflowState = WorkflowState.CREATED,
    ) -> WorkflowRecord:
        now = datetime.now(UTC)
        record = WorkflowRecord(
            workflow_id=workflow_id,
            state=initial_state,
            state_version=1,
            created_at=now,
            updated_at=now,
            revision_count=0,
            failure_reason=None,
        )
        self._workflows[workflow_id] = record
        return record

    def update_workflow_state(
        self,
        workflow_id: str,
        *,
        expected_version: int,
        new_state: WorkflowState,
        failure_reason: str | None = None,
    ) -> WorkflowRecord:
        operation = "update_workflow_state"
        self._require_active_transaction(operation)
        existing = self._workflows.get(workflow_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Workflow {workflow_id} not found")
        if existing.state_version != expected_version:
            raise PersistenceConflictError(
                f"Persistence conflict error during {operation} for entity {workflow_id}"
            )
        now = datetime.now(UTC)
        updated = WorkflowRecord(
            workflow_id=existing.workflow_id,
            state=new_state,
            state_version=existing.state_version + 1,
            created_at=existing.created_at,
            updated_at=now,
            revision_count=existing.revision_count,
            failure_reason=failure_reason,
        )
        self._workflows[workflow_id] = updated
        return updated

    def append_transition(
        self, transition: WorkflowTransitionRecord
    ) -> WorkflowTransitionRecord:
        operation = "append_transition"
        self._require_active_transaction(operation)
        if any(t.transition_id == transition.transition_id for t in self._transitions):
            raise PersistenceDuplicateError(
                f"Duplicate transition_id {transition.transition_id}"
            )
        self._transitions.append(transition)
        return transition

    def list_transitions(
        self, workflow_id: str
    ) -> Sequence[WorkflowTransitionRecord]:
        return sorted(
            (t for t in self._transitions if t.workflow_id == workflow_id),
            key=lambda t: (t.occurred_at, t.transition_id),
        )

    def create_task(
        self,
        task: TaskRecord,
        *,
        payload: JsonValue | None = None,
    ) -> TaskRecord:
        operation = "create_task"
        self._require_active_transaction(operation)
        if task.payload_reference.ref_kind != TASK_PAYLOAD_REF_KIND:
            raise PersistenceValidationError(
                f"Invalid payload ref_kind: {task.payload_reference.ref_kind}"
            )
        payload_body: JsonValue = payload if payload is not None else {}
        self._payloads[task.payload_reference.ref_id] = payload_body
        self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        attempt: int | None = None,
        failure_reason: str | None = None,
        completed_at: datetime | None = None,
    ) -> TaskRecord:
        operation = "update_task"
        self._require_active_transaction(operation)
        existing = self._tasks.get(task_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Task {task_id} not found")
        now = datetime.now(UTC)
        updated = TaskRecord(
            task_id=existing.task_id,
            workflow_id=existing.workflow_id,
            task_type=existing.task_type,
            attempt=attempt if attempt is not None else existing.attempt,
            status=status,
            payload_reference=existing.payload_reference,
            idempotency_key=existing.idempotency_key,
            created_at=existing.created_at,
            updated_at=now,
            completed_at=(
                completed_at if completed_at is not None else existing.completed_at
            ),
            failure_reason=(
                failure_reason
                if failure_reason is not None
                else existing.failure_reason
            ),
        )
        self._tasks[task_id] = updated
        return updated

    def get_task_payload(self, payload_reference: PayloadReference) -> JsonValue:
        if payload_reference.ref_kind != TASK_PAYLOAD_REF_KIND:
            raise PersistenceValidationError(
                f"Invalid payload ref_kind: {payload_reference.ref_kind}"
            )
        if payload_reference.ref_id not in self._payloads:
            raise PersistenceNotFoundError(
                f"Task payload {payload_reference.ref_id} not found"
            )
        return self._payloads[payload_reference.ref_id]
