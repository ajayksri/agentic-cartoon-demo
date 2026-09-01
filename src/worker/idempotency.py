"""Default idempotency orchestrator (LLD §4.3)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Idempotency keys — duplicate queue deliveries must not
# re-run expensive LLM calls; completed keys let duplicate workers ACK safely.
# GUARDRAIL: Execution — at most one authoritative completion per logical operation.

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from config.types import TaskType
from persistence.protocols import ArtifactRepo, IdempotencyRepo
from persistence.types import IdempotencyInsertSpec, IdempotencyOutcome, TaskRecord
from task_queue.types import PendingDelivery

from .constants import LOGICAL_VERSION_FIXED_TYPES
from .types import (
    DuplicateResolution,
    IdempotencyCheckResult,
    IdempotencyClaimResult,
    IdempotencyPhase,
)

if TYPE_CHECKING:
    from persistence.types import ArtifactType


class DefaultIdempotencyOrchestrator:
    """Coordinates idempotency pre-checks and completion claims."""

    def __init__(self, *, idempotency_repo: IdempotencyRepo) -> None:
        self._idempotency_repo = idempotency_repo

    def build_idempotency_key(
        self,
        *,
        workflow_id: str,
        task_type: TaskType,
        logical_version: int,
    ) -> str:
        return f"{workflow_id}:{task_type.value}:{logical_version}"

    def check_before_execution(self, *, idempotency_key: str) -> IdempotencyCheckResult:
        record = self._idempotency_repo.get_by_key(idempotency_key)
        if record is None:
            return IdempotencyCheckResult(
                phase=IdempotencyPhase.NOT_STARTED,
                idempotency_key=idempotency_key,
            )
        return IdempotencyCheckResult(
            phase=IdempotencyPhase.ALREADY_COMPLETED,
            idempotency_key=idempotency_key,
            existing_record=record,
            duplicate_resolution=DuplicateResolution.REUSED_COMMITTED_RESULT,
        )

    def claim_completion(self, *, spec: IdempotencyInsertSpec) -> IdempotencyClaimResult:
        result = self._idempotency_repo.try_insert(spec)
        if result.outcome == IdempotencyOutcome.INSERTED:
            return IdempotencyClaimResult(
                phase=IdempotencyPhase.CLAIMED,
                idempotency_key=spec.idempotency_key,
                record=result.record,
            )
        return IdempotencyClaimResult(
            phase=IdempotencyPhase.DUPLICATE_REJECTED,
            idempotency_key=spec.idempotency_key,
            record=result.record,
            duplicate_resolution=DuplicateResolution.REJECTED_DURING_COMMIT,
        )


def create_idempotency_orchestrator(
    *,
    idempotency_repo: IdempotencyRepo,
) -> DefaultIdempotencyOrchestrator:
    return DefaultIdempotencyOrchestrator(idempotency_repo=idempotency_repo)


def resolve_logical_version(
    *,
    task_type: TaskType,
    task_record: TaskRecord,
    delivery: PendingDelivery,
    artifact_repo: ArtifactRepo,
    workflow_repo: object | None = None,
) -> int:
    """Resolve logical version per LLD §4.3 (LLD-WKR-005 deferred field)."""
    logical_version_attr = getattr(task_record, "logical_version", None)
    if logical_version_attr is not None:
        return int(logical_version_attr)

    if task_type in (TaskType.GENERATE_SCENARIO, TaskType.REVIEW_SCENARIO):
        payload_version = _payload_logical_version(task_record, workflow_repo)
        if payload_version is not None:
            return payload_version

    if task_type == TaskType.REVIEW_SCENARIO:
        from persistence.types import ArtifactType

        active = artifact_repo.get_active_artifact(
            delivery.message.workflow_id,
            ArtifactType.SCENARIO,
        )
        if active is not None:
            content = artifact_repo.get_artifact_content(active.artifact_id)
            if isinstance(content, dict) and "logical_version" in content:
                return int(content["logical_version"])

    if task_type in LOGICAL_VERSION_FIXED_TYPES or task_type == TaskType.GENERATE_SCENARIO:
        return 1

    return 1


def _payload_logical_version(
    task_record: TaskRecord,
    workflow_repo: object | None,
) -> int | None:
    if workflow_repo is None:
        return None
    try:
        payload = workflow_repo.get_task_payload(task_record.payload_reference)
    except Exception:
        return None
    if isinstance(payload, dict) and "logical_version" in payload:
        return int(payload["logical_version"])
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict) and "logical_version" in parsed:
            return int(parsed["logical_version"])
    return None
