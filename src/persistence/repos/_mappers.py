"""Internal row shapes and DB ↔ public record mapping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TypeVar

from persistence.constants import TASK_PAYLOAD_REF_KIND
from persistence.errors import PersistenceValidationError
from persistence.types import (
    AiInvocationRecord,
    ArtifactRecord,
    ArtifactType,
    IdempotencyRecord,
    InvocationStatus,
    OutboxEntry,
    OutboxStatus,
    PayloadReference,
    TaskLease,
    TaskRecord,
    TaskStatus,
    TaskType,
    WorkflowRecord,
    WorkflowState,
    WorkflowTransitionRecord,
)

DbRow = dict[str, object]
JsonParam = dict[str, object] | list[object] | str | int | float | bool | None

_E = TypeVar("_E", WorkflowState, TaskType, ArtifactType, TaskStatus, OutboxStatus, InvocationStatus)


@dataclass
class WorkflowRow:
    workflow_id: str
    state: str
    state_version: int
    created_at: datetime
    updated_at: datetime
    revision_count: int
    failure_reason: str | None


@dataclass
class WorkflowTransitionRow:
    transition_id: str
    workflow_id: str
    from_state: str
    to_state: str
    reason: str
    occurred_at: datetime
    actor: str | None = None


@dataclass
class TaskPayloadRow:
    ref_id: str
    payload: dict[str, object]
    created_at: datetime | None = None


@dataclass
class TaskRow:
    task_id: str
    workflow_id: str
    task_type: str
    status: str
    attempt: int
    payload_ref_id: str
    payload_ref_kind: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    failure_reason: str | None = None
    completed_at: datetime | None = None


@dataclass
class ArtifactRow:
    artifact_id: str
    workflow_id: str
    artifact_type: str
    name: str
    version: int
    logical_version: int
    is_active: bool
    created_at: datetime
    content_hash: str | None = None


@dataclass
class ArtifactContentRow:
    artifact_id: str
    content: dict[str, object]
    created_at: datetime | None = None


@dataclass
class IdempotencyRow:
    idempotency_key: str
    workflow_id: str
    task_id: str
    completed_at: datetime
    result_artifact_id: str | None = None


@dataclass
class OutboxRow:
    outbox_id: str
    workflow_id: str
    task_id: str
    task_type: str
    payload_ref_id: str
    payload_ref_kind: str
    idempotency_key: str
    status: str
    created_at: datetime
    published_at: datetime | None = None


@dataclass
class TaskLeaseRow:
    lease_id: str
    task_id: str
    worker_id: str
    acquired_at: datetime
    expires_at: datetime


@dataclass
class AiInvocationRow:
    invocation_id: str
    workflow_id: str
    task_id: str
    agent_name: str
    agent_version: str
    prompt_version: str
    provider: str
    model: str
    input_artifact_id: str | None
    output_artifact_id: str | None
    attempt: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


class RowMapper:
    """Stateless; maps DB string tokens ↔ persistence public enums."""

    def workflow_state_to_db(self, state: WorkflowState) -> str:
        return state.value

    def workflow_state_from_db(self, token: str) -> WorkflowState:
        return self._enum_from_db(WorkflowState, token, "workflow state")

    def task_type_to_db(self, task_type: TaskType) -> str:
        return task_type.value

    def task_type_from_db(self, token: str) -> TaskType:
        return self._enum_from_db(TaskType, token, "task type")

    def artifact_type_to_db(self, artifact_type: ArtifactType) -> str:
        return artifact_type.value

    def artifact_type_from_db(self, token: str) -> ArtifactType:
        return self._enum_from_db(ArtifactType, token, "artifact type")

    def task_status_to_db(self, status: TaskStatus) -> str:
        return status.value

    def task_status_from_db(self, token: str) -> TaskStatus:
        return self._enum_from_db(TaskStatus, token, "task status")

    def outbox_status_to_db(self, status: OutboxStatus) -> str:
        return status.value

    def outbox_status_from_db(self, token: str) -> OutboxStatus:
        return self._enum_from_db(OutboxStatus, token, "outbox status")

    def invocation_status_to_db(self, status: InvocationStatus) -> str:
        return status.value

    def invocation_status_from_db(self, token: str) -> InvocationStatus:
        return self._enum_from_db(InvocationStatus, token, "invocation status")

    def to_workflow_record(self, row: WorkflowRow) -> WorkflowRecord:
        return WorkflowRecord(
            workflow_id=row.workflow_id,
            state=self.workflow_state_from_db(row.state),
            state_version=row.state_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            revision_count=row.revision_count,
            failure_reason=row.failure_reason,
        )

    def to_workflow_transition_record(
        self, row: WorkflowTransitionRow
    ) -> WorkflowTransitionRecord:
        return WorkflowTransitionRecord(
            transition_id=row.transition_id,
            workflow_id=row.workflow_id,
            from_state=self.workflow_state_from_db(row.from_state),
            to_state=self.workflow_state_from_db(row.to_state),
            reason=row.reason,
            occurred_at=row.occurred_at,
            actor=row.actor,
        )

    def to_task_record(self, row: DbRow, payload_ref: PayloadReference) -> TaskRecord:
        return TaskRecord(
            task_id=str(row["task_id"]),
            workflow_id=str(row["workflow_id"]),
            task_type=self.task_type_from_db(str(row["task_type"])),
            attempt=int(row["attempt"]),  # type: ignore[arg-type]
            status=self.task_status_from_db(str(row["status"])),
            payload_reference=payload_ref,
            idempotency_key=str(row["idempotency_key"]),
            created_at=row["created_at"],  # type: ignore[arg-type]
            updated_at=row["updated_at"],  # type: ignore[arg-type]
            completed_at=row.get("completed_at"),  # type: ignore[arg-type]
            failure_reason=(
                str(row["failure_reason"])
                if row.get("failure_reason") is not None
                else None
            ),
        )

    def to_task_record_from_row(self, row: TaskRow) -> TaskRecord:
        return self.to_task_record(
            {
                "task_id": row.task_id,
                "workflow_id": row.workflow_id,
                "task_type": row.task_type,
                "status": row.status,
                "attempt": row.attempt,
                "idempotency_key": row.idempotency_key,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "completed_at": row.completed_at,
                "failure_reason": row.failure_reason,
            },
            PayloadReference(
                ref_id=row.payload_ref_id,
                ref_kind=row.payload_ref_kind,
            ),
        )

    def to_artifact_record(self, row: ArtifactRow) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row.artifact_id,
            workflow_id=row.workflow_id,
            artifact_type=self.artifact_type_from_db(row.artifact_type),
            name=row.name,
            version=row.version,
            logical_version=row.logical_version,
            is_active=row.is_active,
            created_at=row.created_at,
            content_hash=row.content_hash,
        )

    def to_idempotency_record(self, row: IdempotencyRow) -> IdempotencyRecord:
        return IdempotencyRecord(
            idempotency_key=row.idempotency_key,
            workflow_id=row.workflow_id,
            task_id=row.task_id,
            completed_at=row.completed_at,
            result_artifact_id=row.result_artifact_id,
        )

    def to_outbox_entry(self, row: OutboxRow) -> OutboxEntry:
        return OutboxEntry(
            outbox_id=row.outbox_id,
            workflow_id=row.workflow_id,
            task_id=row.task_id,
            task_type=self.task_type_from_db(row.task_type),
            payload_reference=PayloadReference(
                ref_id=row.payload_ref_id,
                ref_kind=row.payload_ref_kind,
            ),
            idempotency_key=row.idempotency_key,
            status=self.outbox_status_from_db(row.status),
            created_at=row.created_at,
            published_at=row.published_at,
        )

    def to_task_lease(self, row: TaskLeaseRow) -> TaskLease:
        return TaskLease(
            lease_id=row.lease_id,
            task_id=row.task_id,
            worker_id=row.worker_id,
            acquired_at=row.acquired_at,
            expires_at=row.expires_at,
        )

    def to_ai_invocation_record(self, row: AiInvocationRow) -> AiInvocationRecord:
        return AiInvocationRecord(
            invocation_id=row.invocation_id,
            workflow_id=row.workflow_id,
            task_id=row.task_id,
            agent_name=row.agent_name,
            agent_version=row.agent_version,
            prompt_version=row.prompt_version,
            provider=row.provider,
            model=row.model,
            input_artifact_id=row.input_artifact_id,
            output_artifact_id=row.output_artifact_id,
            attempt=row.attempt,
            started_at=row.started_at,
            completed_at=row.completed_at,
            status=self.invocation_status_from_db(row.status),
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            estimated_cost_usd=row.estimated_cost_usd,
        )

    def payload_reference_from_task_row(self, row: TaskRow) -> PayloadReference:
        return PayloadReference(
            ref_id=row.payload_ref_id,
            ref_kind=row.payload_ref_kind or TASK_PAYLOAD_REF_KIND,
        )

    def _enum_from_db(self, enum_cls: type[_E], token: str, label: str) -> _E:
        try:
            return enum_cls(token)
        except ValueError as exc:
            raise PersistenceValidationError(
                f"Unknown {label} token: {token}"
            ) from exc
