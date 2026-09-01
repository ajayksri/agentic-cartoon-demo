"""In-memory workflow repository fake with duck-typed extensions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from persistence.constants import TASK_PAYLOAD_REF_KIND
from persistence.errors import PersistenceConflictError, PersistenceNotFoundError
from persistence.types import (
    JsonValue,
    PayloadReference,
    TaskRecord,
    TaskStatus,
    TaskType,
    WorkflowRecord,
    WorkflowState,
    WorkflowTransitionRecord,
)

_TERMINAL_STATES = frozenset(
    {
        WorkflowState.NO_SUITABLE_TOPIC,
        WorkflowState.APPROVED,
        WorkflowState.REJECTED,
        WorkflowState.REVIEW_FAILED,
        WorkflowState.FAILED,
        WorkflowState.FAILED_PERMANENTLY,
    }
)

_OLD_ENOUGH = datetime(2020, 1, 1, tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class InMemoryWorkflowRepo:
    """Dict-backed workflow repository for workflow contract tests."""

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowRecord] = {}
        self._transitions: list[WorkflowTransitionRecord] = []
        self._tasks: dict[str, TaskRecord] = {}
        self._payloads: dict[str, JsonValue] = {}
        self._ai_invocations: list[object] = []
        self._seed_contract_fixtures()

    def _seed_contract_fixtures(self) -> None:
        fixtures: list[tuple[str, WorkflowState, int, int, str | None]] = [
            ("wf-terminal-approved", WorkflowState.APPROVED, 1, 0, None),
            ("wf-no-topic", WorkflowState.SELECTING_TOPIC, 1, 0, None),
            ("wf-unrecoverable", WorkflowState.GENERATING_SCENARIO, 1, 0, None),
            ("wf-retries-exhausted", WorkflowState.REVIEWING, 1, 0, None),
            ("wf-critic-pass", WorkflowState.REVIEWING, 1, 0, None),
            ("wf-approve", WorkflowState.AWAITING_HUMAN_APPROVAL, 1, 0, None),
            ("wf-awaiting-approval", WorkflowState.REVIEWING, 1, 0, None),
            ("wf-regenerate", WorkflowState.AWAITING_HUMAN_APPROVAL, 1, 0, None),
            ("wf-already-approved", WorkflowState.APPROVED, 1, 0, None),
            ("wf-revise-loop", WorkflowState.REVIEWING, 1, 0, None),
            ("wf-max-revisions", WorkflowState.REVIEWING, 1, 2, None),
            ("wf-output-complete", WorkflowState.APPROVED, 1, 0, None),
            (
                "wf-output-failed",
                WorkflowState.FAILED,
                1,
                0,
                "provider_failure",
            ),
            ("wf-read-only", WorkflowState.COLLECTED, 1, 0, None),
            ("wf-rp001-collected", WorkflowState.COLLECTED, 1, 0, None),
        ]
        for workflow_id, state, version, revision_count, failure_reason in fixtures:
            updated_at = _now() if workflow_id == "wf-rp001-collected" else _OLD_ENOUGH
            self._workflows[workflow_id] = WorkflowRecord(
                workflow_id=workflow_id,
                state=state,
                state_version=version,
                created_at=_OLD_ENOUGH,
                updated_at=updated_at,
                revision_count=revision_count,
                failure_reason=failure_reason,
            )

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        return self._workflows.get(workflow_id)

    def create_workflow(
        self,
        workflow_id_or_record: str | WorkflowRecord,
        *,
        initial_state: WorkflowState = WorkflowState.CREATED,
    ) -> WorkflowRecord:
        if isinstance(workflow_id_or_record, WorkflowRecord):
            record = workflow_id_or_record
            self._workflows[record.workflow_id] = record
            return record
        workflow_id = workflow_id_or_record
        now = _now()
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
        revision_count: int | None = None,
    ) -> WorkflowRecord:
        existing = self._workflows.get(workflow_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Workflow {workflow_id} not found")
        if existing.state_version != expected_version:
            raise PersistenceConflictError(
                f"Persistence conflict error during update_workflow_state for entity {workflow_id}"
            )
        now = _now()
        updated = WorkflowRecord(
            workflow_id=existing.workflow_id,
            state=new_state,
            state_version=existing.state_version + 1,
            created_at=existing.created_at,
            updated_at=now,
            revision_count=(
                revision_count if revision_count is not None else existing.revision_count
            ),
            failure_reason=failure_reason,
        )
        self._workflows[workflow_id] = updated
        return updated

    def append_transition(
        self, transition: WorkflowTransitionRecord
    ) -> WorkflowTransitionRecord:
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
        existing = self._tasks.get(task_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Task {task_id} not found")
        now = _now()
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
            completed_at=completed_at if completed_at is not None else existing.completed_at,
            failure_reason=(
                failure_reason if failure_reason is not None else existing.failure_reason
            ),
        )
        self._tasks[task_id] = updated
        return updated

    def get_task_payload(self, payload_reference: PayloadReference) -> JsonValue:
        if payload_reference.ref_id not in self._payloads:
            raise PersistenceNotFoundError(
                f"Task payload {payload_reference.ref_id} not found"
            )
        return self._payloads[payload_reference.ref_id]

    def list_tasks_for_workflow(self, workflow_id: str) -> Sequence[TaskRecord]:
        tasks = [t for t in self._tasks.values() if t.workflow_id == workflow_id]
        return sorted(tasks, key=lambda t: t.created_at)

    def list_workflows_for_reconciliation(
        self,
        *,
        states: Sequence[WorkflowState],
        updated_before: datetime | None = None,
        limit: int,
    ) -> Sequence[WorkflowRecord]:
        state_set = set(states)
        rows = [
            w
            for w in self._workflows.values()
            if w.state in state_set
            and w.state not in _TERMINAL_STATES
            and (updated_before is None or w.updated_at < updated_before)
        ]
        rows.sort(key=lambda w: w.updated_at)
        return rows[:limit]

    def list_ai_invocations(self, workflow_id: str) -> Sequence[object]:
        return [inv for inv in self._ai_invocations if inv.workflow_id == workflow_id]  # type: ignore[attr-defined]

    def seed_timeline_collision(
        self,
        *,
        workflow_id: str,
        occurred_at: datetime,
        transition_ids: tuple[str, ...],
        task_ids: tuple[str, ...],
        invocation_ids: tuple[str, ...],
    ) -> None:
        if workflow_id not in self._workflows:
            self.create_workflow(workflow_id, initial_state=WorkflowState.COLLECTED)
        for transition_id in transition_ids:
            self._transitions.append(
                WorkflowTransitionRecord(
                    transition_id=transition_id,
                    workflow_id=workflow_id,
                    from_state=WorkflowState.COLLECTED,
                    to_state=WorkflowState.SELECTING_TOPIC,
                    reason="seeded",
                    occurred_at=occurred_at,
                )
            )
        for task_id in task_ids:
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                workflow_id=workflow_id,
                task_type=TaskType.COLLECT,
                attempt=1,
                status=TaskStatus.PENDING,
                payload_reference=PayloadReference(
                    ref_id=task_id, ref_kind=TASK_PAYLOAD_REF_KIND
                ),
                idempotency_key=f"{workflow_id}:COLLECT:1",
                created_at=occurred_at,
                updated_at=occurred_at,
            )
