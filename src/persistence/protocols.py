"""Public persistence repository protocols."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from .types import (
    AiInvocationInsertSpec,
    AiInvocationRecord,
    ArtifactCreateSpec,
    ArtifactRecord,
    ArtifactType,
    IdempotencyInsertResult,
    IdempotencyInsertSpec,
    IdempotencyRecord,
    JsonValue,
    OutboxEntry,
    OutboxInsertSpec,
    PayloadReference,
    TaskLease,
    TaskRecord,
    TaskStatus,
    WorkflowRecord,
    WorkflowState,
    WorkflowTransitionRecord,
)


class WorkflowRepo(Protocol):
    """Workflows, transition history, tasks, and task payloads."""

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Fetch the current workflow row."""
        ...

    def create_workflow(
        self,
        workflow_id: str,
        *,
        initial_state: WorkflowState = WorkflowState.CREATED,
    ) -> WorkflowRecord:
        """Insert a new workflow record."""
        ...

    def update_workflow_state(
        self,
        workflow_id: str,
        *,
        expected_version: int,
        new_state: WorkflowState,
        failure_reason: str | None = None,
    ) -> WorkflowRecord:
        """Optimistic workflow state update."""
        ...

    def append_transition(
        self, transition: WorkflowTransitionRecord
    ) -> WorkflowTransitionRecord:
        """Append an immutable transition history record."""
        ...

    def list_transitions(
        self, workflow_id: str
    ) -> Sequence[WorkflowTransitionRecord]:
        """Return ordered transition history for a workflow."""
        ...

    def create_task(self, task: TaskRecord) -> TaskRecord:
        """Insert a task envelope."""
        ...

    def get_task(self, task_id: str) -> TaskRecord | None:
        """Fetch a task by identifier."""
        ...

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        attempt: int | None = None,
        failure_reason: str | None = None,
        completed_at: datetime | None = None,
    ) -> TaskRecord:
        """Update task lifecycle fields."""
        ...

    def get_task_payload(self, payload_reference: PayloadReference) -> JsonValue:
        """Load durable task payload content."""
        ...


class ArtifactRepo(Protocol):
    """Artifact metadata, JSONB content, and AI invocation audit records."""

    def create_artifact(self, spec: ArtifactCreateSpec) -> ArtifactRecord:
        """Insert artifact metadata and immutable JSONB content."""
        ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        """Fetch artifact metadata."""
        ...

    def get_artifact_content(self, artifact_id: str) -> JsonValue:
        """Fetch immutable artifact JSONB content."""
        ...

    def list_artifacts(
        self,
        workflow_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        active_only: bool = False,
    ) -> Sequence[ArtifactRecord]:
        """List artifact versions for a workflow."""
        ...

    def get_active_artifact(
        self, workflow_id: str, artifact_type: ArtifactType
    ) -> ArtifactRecord | None:
        """Return the active artifact for a workflow and type."""
        ...

    def append_ai_invocation(
        self, spec: AiInvocationInsertSpec
    ) -> AiInvocationRecord:
        """Append an AI invocation audit record."""
        ...

    def list_ai_invocations(
        self, workflow_id: str, *, task_id: str | None = None
    ) -> Sequence[AiInvocationRecord]:
        """List AI invocation audit records."""
        ...


class IdempotencyRepo(Protocol):
    """Insert-once idempotency records."""

    def try_insert(self, spec: IdempotencyInsertSpec) -> IdempotencyInsertResult:
        """Insert an idempotency record or detect a duplicate key."""
        ...

    def get_by_key(self, idempotency_key: str) -> IdempotencyRecord | None:
        """Lookup a completed operation by idempotency key."""
        ...


class OutboxRepo(Protocol):
    """Transactional outbox for at-least-once task dispatch."""

    def insert(self, spec: OutboxInsertSpec) -> OutboxEntry:
        """Insert an unpublished outbox row."""
        ...

    def fetch_unpublished(self, limit: int) -> Sequence[OutboxEntry]:
        """Fetch unpublished outbox rows for the coordinator publisher."""
        ...

    def mark_published(
        self, outbox_id: str, *, published_at: datetime
    ) -> OutboxEntry:
        """Mark an outbox row as published."""
        ...


class TaskLeaseRepo(Protocol):
    """Short-lived in-flight task leases."""

    def try_acquire(
        self, task_id: str, *, worker_id: str, ttl_seconds: float
    ) -> TaskLease | None:
        """Acquire a lease or return None when another worker holds it."""
        ...

    def renew(self, lease_id: str, *, ttl_seconds: float) -> TaskLease:
        """Extend lease expiry."""
        ...

    def release(self, lease_id: str) -> None:
        """Release a task lease."""
        ...

    def get_active_lease(self, task_id: str) -> TaskLease | None:
        """Return the active unexpired lease for a task, if any."""
        ...


class TransactionManager(Protocol):
    """Unit-of-work boundary for atomic multi-repository commits."""

    def transaction(self) -> AbstractContextManager[None]:
        """Begin a transaction scope shared by repository operations."""
        ...
