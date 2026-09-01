"""Outbox task spec builder and logical version tracking (LLD §4, §10)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Payload-by-reference — large artifacts stay in
# PostgreSQL; queue messages carry only pointers, keeping Redis messages small.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from config.types import TaskType
from persistence.constants import TASK_PAYLOAD_REF_KIND
from persistence.protocols import ArtifactRepo
from persistence.types import (
    OutboxInsertSpec,
    PayloadReference,
    TaskRecord,
    TaskStatus,
    WorkflowRecord,
    ArtifactType,
)

from .transition_table import ApprovalDecision, TransitionDecision
from .types import OutboxTaskSpec


@dataclass(frozen=True, slots=True)
class OutboxBuildResult:
    """Fully materialized dispatch artifacts ready for TransitionExecutor."""

    task_spec: OutboxTaskSpec
    task_record: TaskRecord
    outbox_insert: OutboxInsertSpec
    payload_json: dict[str, object]


class LogicalVersionTracker:
    """Resolves logical_version for idempotency keys from artifact metadata."""

    def resolve_for_task(
        self,
        *,
        workflow_id: str,
        task_type: TaskType,
        artifact_repo: ArtifactRepo,
        increment: bool = False,
    ) -> int:
        if task_type in {TaskType.COLLECT, TaskType.SELECT_TOPIC}:
            return 1
        active_scenario = artifact_repo.get_active_artifact(
            workflow_id, ArtifactType.SCENARIO
        )
        current = active_scenario.logical_version if active_scenario else 0
        base = max(current, 1)
        return base + 1 if increment else base


def format_idempotency_key(
    *, workflow_id: str, task_type: TaskType, logical_version: int
) -> str:
    return f"{workflow_id}:{task_type.value}:{logical_version}"


def _payload_for_task_type(task_type: TaskType, logical_version: int) -> dict[str, object]:
    if task_type in {TaskType.COLLECT, TaskType.SELECT_TOPIC}:
        return {}
    return {"logical_version": logical_version}


class OutboxSpecBuilder:
    """Generates task/outbox specs without repository I/O."""

    def __init__(
        self,
        *,
        logical_version_tracker: LogicalVersionTracker,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._logical_version_tracker = logical_version_tracker
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(
        self,
        *,
        workflow: WorkflowRecord,
        task_type: TaskType,
        logical_version: int,
        attempt: int = 1,
    ) -> OutboxBuildResult:
        now = self._clock()
        task_id = str(uuid4())
        payload_json = _payload_for_task_type(task_type, logical_version)
        payload_ref = PayloadReference(ref_id=task_id, ref_kind=TASK_PAYLOAD_REF_KIND)
        idempotency_key = format_idempotency_key(
            workflow_id=workflow.workflow_id,
            task_type=task_type,
            logical_version=logical_version,
        )
        task_spec = OutboxTaskSpec(
            task_id=task_id,
            workflow_id=workflow.workflow_id,
            task_type=task_type,
            attempt=attempt,
            payload_reference=task_id,
            idempotency_key=idempotency_key,
            created_at=now,
        )
        task_record = TaskRecord(
            task_id=task_id,
            workflow_id=workflow.workflow_id,
            task_type=task_type,
            attempt=attempt,
            status=TaskStatus.PENDING,
            payload_reference=payload_ref,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        outbox_insert = OutboxInsertSpec(
            workflow_id=workflow.workflow_id,
            task_id=task_id,
            task_type=task_type,
            payload_reference=payload_ref,
            idempotency_key=idempotency_key,
        )
        return OutboxBuildResult(
            task_spec=task_spec,
            task_record=task_record,
            outbox_insert=outbox_insert,
            payload_json=payload_json,
        )

    def build_for_decision(
        self,
        *,
        workflow: WorkflowRecord,
        decision: TransitionDecision | ApprovalDecision,
        artifact_repo: ArtifactRepo,
    ) -> OutboxBuildResult | None:
        task_type = decision.outbox_task_type
        if task_type is None:
            return None
        increment = getattr(decision, "increment_logical_version", False)
        logical_version = self._logical_version_tracker.resolve_for_task(
            workflow_id=workflow.workflow_id,
            task_type=task_type,
            artifact_repo=artifact_repo,
            increment=increment,
        )
        return self.build(
            workflow=workflow,
            task_type=task_type,
            logical_version=logical_version,
        )
