"""PostgreSQL workflow repository implementation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from psycopg.errors import UniqueViolation

from persistence.constants import TASK_PAYLOAD_REF_KIND
from persistence.errors import (
    PersistenceConflictError,
    PersistenceDuplicateError,
    PersistenceNotFoundError,
    PersistenceValidationError,
)
from persistence.repos._base import PostgresRepoBase, _jsonb
from persistence.repos._mappers import WorkflowRow, WorkflowTransitionRow
from persistence.repos._sql import TASK_PAYLOADS, TASKS, WORKFLOW_TRANSITIONS, WORKFLOWS
from persistence.types import (
    JsonValue,
    PayloadReference,
    TaskRecord,
    TaskStatus,
    WorkflowRecord,
    WorkflowState,
    WorkflowTransitionRecord,
)


class PostgresWorkflowRepo(PostgresRepoBase):
    """Workflows, transition history, tasks, and task payloads."""

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        operation = "get_workflow"
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    WORKFLOWS,
                    (workflow_id,),
                    prepare=False,
                ).fetchone()
            if row is None:
                return None
            record = self._mapper.to_workflow_record(self._workflow_row_from_dict(row))
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

    def create_workflow(
        self,
        workflow_id: str,
        *,
        initial_state: WorkflowState = WorkflowState.CREATED,
    ) -> WorkflowRecord:
        operation = "create_workflow"
        now = datetime.now(UTC)
        state_token = self._mapper.workflow_state_to_db(initial_state)
        try:
            with self._borrow_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO workflows (
                        workflow_id, state, state_version, revision_count,
                        failure_reason, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (workflow_id, state_token, 1, 0, None, now, now),
                    prepare=False,
                )
            record = WorkflowRecord(
                workflow_id=workflow_id,
                state=initial_state,
                state_version=1,
                created_at=now,
                updated_at=now,
                revision_count=0,
                failure_reason=None,
            )
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

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
        now = datetime.now(UTC)
        state_token = self._mapper.workflow_state_to_db(new_state)
        try:
            conn = self._connection()
            cursor = conn.execute(
                """
                UPDATE workflows
                SET state = %s,
                    state_version = state_version + 1,
                    updated_at = %s,
                    failure_reason = %s
                WHERE workflow_id = %s AND state_version = %s
                RETURNING workflow_id, state, state_version, revision_count,
                          failure_reason, created_at, updated_at
                """,
                (
                    state_token,
                    now,
                    failure_reason,
                    workflow_id,
                    expected_version,
                ),
                prepare=False,
            )
            if cursor.rowcount == 0:
                if self._workflow_exists(workflow_id):
                    conflict = PersistenceConflictError(
                        f"Persistence conflict error during {operation} "
                        f"for entity {workflow_id}"
                    )
                    self._log_error(operation, conflict, workflow_id)
                    raise conflict
                not_found = PersistenceNotFoundError(
                    f"Workflow {workflow_id} not found"
                )
                self._log_error(operation, not_found, workflow_id)
                raise not_found
            row = cursor.fetchone()
            record = self._mapper.to_workflow_record(
                self._workflow_row_from_dict(row)
            )
            self._record_success(operation)
            return record
        except (
            PersistenceConflictError,
            PersistenceNotFoundError,
            PersistenceValidationError,
        ):
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

    def append_transition(
        self, transition: WorkflowTransitionRecord
    ) -> WorkflowTransitionRecord:
        operation = "append_transition"
        self._require_active_transaction(operation)
        try:
            conn = self._connection()
            conn.execute(
                WORKFLOW_TRANSITIONS,
                (
                    transition.transition_id,
                    transition.workflow_id,
                    self._mapper.workflow_state_to_db(transition.from_state),
                    self._mapper.workflow_state_to_db(transition.to_state),
                    transition.reason,
                    transition.actor,
                    transition.occurred_at,
                ),
                prepare=False,
            )
            self._record_success(operation)
            return transition
        except UniqueViolation as exc:
            duplicate = PersistenceDuplicateError(
                f"Duplicate transition_id {transition.transition_id}"
            )
            self._log_error(operation, duplicate, transition.transition_id)
            raise duplicate from exc
        except Exception as exc:
            self._raise_mapped(
                exc, operation=operation, entity_id=transition.transition_id
            )

    def list_transitions(
        self, workflow_id: str
    ) -> Sequence[WorkflowTransitionRecord]:
        operation = "list_transitions"
        try:
            with self._borrow_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT transition_id, workflow_id, from_state, to_state,
                           reason, actor, occurred_at
                    FROM workflow_transitions
                    WHERE workflow_id = %s
                    ORDER BY occurred_at ASC, id ASC
                    """,
                    (workflow_id,),
                    prepare=False,
                ).fetchall()
            records = [
                self._mapper.to_workflow_transition_record(
                    WorkflowTransitionRow(
                        transition_id=str(row["transition_id"]),
                        workflow_id=str(row["workflow_id"]),
                        from_state=str(row["from_state"]),
                        to_state=str(row["to_state"]),
                        reason=str(row["reason"]),
                        occurred_at=row["occurred_at"],  # type: ignore[arg-type]
                        actor=(
                            str(row["actor"])
                            if row.get("actor") is not None
                            else None
                        ),
                    )
                )
                for row in rows
            ]
            self._record_success(operation)
            return records
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

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
        try:
            conn = self._connection()
            now = datetime.now(UTC)
            conn.execute(
                TASK_PAYLOADS,
                (task.payload_reference.ref_id, _jsonb(payload_body), now),
                prepare=False,
            )
            conn.execute(
                TASKS,
                (
                    task.task_id,
                    task.workflow_id,
                    self._mapper.task_type_to_db(task.task_type),
                    self._mapper.task_status_to_db(task.status),
                    task.attempt,
                    task.payload_reference.ref_id,
                    task.payload_reference.ref_kind,
                    task.idempotency_key,
                    task.failure_reason,
                    task.created_at,
                    task.updated_at,
                    task.completed_at,
                ),
                prepare=False,
            )
            self._record_success(operation)
            return task
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=task.task_id)

    def get_task(self, task_id: str) -> TaskRecord | None:
        operation = "get_task"
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    SELECT task_id, workflow_id, task_type, status, attempt,
                           payload_ref_id, payload_ref_kind, idempotency_key,
                           failure_reason, created_at, updated_at, completed_at
                    FROM tasks
                    WHERE task_id = %s
                    """,
                    (task_id,),
                    prepare=False,
                ).fetchone()
            if row is None:
                return None
            record = self._mapper.to_task_record(
                row,
                PayloadReference(
                    ref_id=str(row["payload_ref_id"]),
                    ref_kind=str(row["payload_ref_kind"]),
                ),
            )
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=task_id)

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
        now = datetime.now(UTC)
        status_token = self._mapper.task_status_to_db(status)
        try:
            conn = self._connection()
            row = conn.execute(
                """
                UPDATE tasks
                SET status = %s,
                    updated_at = %s,
                    attempt = CASE WHEN %s::integer IS NOT NULL THEN %s::integer ELSE attempt END,
                    failure_reason = CASE
                        WHEN %s::text IS NOT NULL THEN %s::text ELSE failure_reason END,
                    completed_at = CASE
                        WHEN %s::timestamptz IS NOT NULL THEN %s::timestamptz ELSE completed_at END
                WHERE task_id = %s
                RETURNING task_id, workflow_id, task_type, status, attempt,
                          payload_ref_id, payload_ref_kind, idempotency_key,
                          failure_reason, created_at, updated_at, completed_at
                """,
                (
                    status_token,
                    now,
                    attempt,
                    attempt,
                    failure_reason,
                    failure_reason,
                    completed_at,
                    completed_at,
                    task_id,
                ),
                prepare=False,
            ).fetchone()
            if row is None:
                not_found = PersistenceNotFoundError(f"Task {task_id} not found")
                self._log_error(operation, not_found, task_id)
                raise not_found
            record = self._mapper.to_task_record(
                row,
                PayloadReference(
                    ref_id=str(row["payload_ref_id"]),
                    ref_kind=str(row["payload_ref_kind"]),
                ),
            )
            self._record_success(operation)
            return record
        except PersistenceNotFoundError:
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=task_id)

    def get_task_payload(self, payload_reference: PayloadReference) -> JsonValue:
        operation = "get_task_payload"
        if payload_reference.ref_kind != TASK_PAYLOAD_REF_KIND:
            raise PersistenceValidationError(
                f"Invalid payload ref_kind: {payload_reference.ref_kind}"
            )
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    SELECT payload
                    FROM task_payloads
                    WHERE ref_id = %s
                    """,
                    (payload_reference.ref_id,),
                    prepare=False,
                ).fetchone()
            if row is None:
                not_found = PersistenceNotFoundError(
                    f"Task payload {payload_reference.ref_id} not found"
                )
                self._log_error(operation, not_found, payload_reference.ref_id)
                raise not_found
            self._record_success(operation)
            return row["payload"]  # type: ignore[return-value]
        except PersistenceNotFoundError:
            raise
        except Exception as exc:
            self._raise_mapped(
                exc, operation=operation, entity_id=payload_reference.ref_id
            )

    def _workflow_exists(self, workflow_id: str) -> bool:
        with self._borrow_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM workflows WHERE workflow_id = %s",
                (workflow_id,),
                prepare=False,
            ).fetchone()
        return row is not None

    @staticmethod
    def _workflow_row_from_dict(row: dict[str, Any]) -> WorkflowRow:
        return WorkflowRow(
            workflow_id=str(row["workflow_id"]),
            state=str(row["state"]),
            state_version=int(row["state_version"]),  # type: ignore[arg-type]
            created_at=row["created_at"],  # type: ignore[arg-type]
            updated_at=row["updated_at"],  # type: ignore[arg-type]
            revision_count=int(row["revision_count"]),  # type: ignore[arg-type]
            failure_reason=(
                str(row["failure_reason"])
                if row.get("failure_reason") is not None
                else None
            ),
        )
