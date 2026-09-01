"""Pre-code test mold for WKR-002 — IdempotencyOrchestrator (LLD §4.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.types import TaskType
from persistence.fakes.idempotency import InMemoryIdempotencyRepo
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import IdempotencyInsertSpec
from worker import (
    DuplicateResolution,
    IdempotencyPhase,
    create_idempotency_orchestrator,
)

_WORKFLOW_ID = "wf-idem-1"
_LOGICAL_VERSION = 1


def _orchestrator() -> object:
    txn = InMemoryTransactionManager()
    repo = InMemoryIdempotencyRepo(transaction_manager=txn)
    return create_idempotency_orchestrator(idempotency_repo=repo), txn, repo


@pytest.mark.wkr_tc("012")
def test_build_idempotency_key_stable_for_same_inputs() -> None:
    """WKR-TC-012: identical key for same workflow, task type, logical version."""
    orchestrator, _, _ = _orchestrator()
    key_a = orchestrator.build_idempotency_key(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.COLLECT,
        logical_version=_LOGICAL_VERSION,
    )
    key_b = orchestrator.build_idempotency_key(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.COLLECT,
        logical_version=_LOGICAL_VERSION,
    )
    assert key_a == key_b
    assert key_a == f"{_WORKFLOW_ID}:COLLECT:{_LOGICAL_VERSION}"


def test_build_idempotency_key_uses_task_type_value() -> None:
    """LLD §4.3: key format uses config TaskType.value string."""
    orchestrator, _, _ = _orchestrator()
    key = orchestrator.build_idempotency_key(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.GENERATE_SCENARIO,
        logical_version=2,
    )
    assert key == f"{_WORKFLOW_ID}:GENERATE_SCENARIO:2"


def test_check_before_execution_returns_not_started_when_absent() -> None:
    orchestrator, _, _ = _orchestrator()
    key = orchestrator.build_idempotency_key(  # type: ignore[attr-defined]
        workflow_id=_WORKFLOW_ID,
        task_type=TaskType.COLLECT,
        logical_version=1,
    )
    result = orchestrator.check_before_execution(idempotency_key=key)  # type: ignore[attr-defined]
    assert result.phase == IdempotencyPhase.NOT_STARTED
    assert result.duplicate_resolution is None


def test_check_before_execution_returns_already_completed_when_record_exists() -> None:
    """WKR-TC-010/015 seam: pre-check short-circuit when record present."""
    orchestrator, txn, repo = _orchestrator()
    key = f"{_WORKFLOW_ID}:COLLECT:1"
    spec = IdempotencyInsertSpec(
        idempotency_key=key,
        workflow_id=_WORKFLOW_ID,
        task_id="task-1",
        result_artifact_id="art-1",
    )
    with txn.transaction():
        repo.try_insert(spec)
    result = orchestrator.check_before_execution(idempotency_key=key)  # type: ignore[attr-defined]
    assert result.phase == IdempotencyPhase.ALREADY_COMPLETED
    assert result.duplicate_resolution in {
        DuplicateResolution.REUSED_COMMITTED_RESULT,
        DuplicateResolution.IGNORED_BEFORE_EXECUTION,
    }


@pytest.mark.wkr_tc("013")
def test_claim_completion_first_claimed_second_duplicate_rejected() -> None:
    """WKR-TC-013: first CLAIMED, second DUPLICATE_REJECTED at orchestrator seam."""
    orchestrator, txn, _ = _orchestrator()
    key = f"{_WORKFLOW_ID}:SELECT_TOPIC:1"
    spec = IdempotencyInsertSpec(
        idempotency_key=key,
        workflow_id=_WORKFLOW_ID,
        task_id="task-claim-1",
        result_artifact_id="art-topic-1",
    )
    with txn.transaction():
        first = orchestrator.claim_completion(spec=spec)  # type: ignore[attr-defined]
    assert first.phase == IdempotencyPhase.CLAIMED
    with txn.transaction():
        second = orchestrator.claim_completion(spec=spec)  # type: ignore[attr-defined]
    assert second.phase == IdempotencyPhase.DUPLICATE_REJECTED
    assert second.duplicate_resolution == DuplicateResolution.REJECTED_DURING_COMMIT


def test_resolve_logical_version_defaults_for_collect() -> None:
    """LLD §4.3: COLLECT defaults to logical version 1."""
    from worker.idempotency import resolve_logical_version

    from persistence import PayloadReference, TaskRecord, TaskStatus
    from persistence.types import TaskType as PersTaskType
    from task_queue import PendingDelivery, TaskMessage

    now = datetime.now(UTC)
    task = TaskRecord(
        task_id="task-collect-1",
        workflow_id=_WORKFLOW_ID,
        task_type=PersTaskType.COLLECT,
        attempt=1,
        status=TaskStatus.PENDING,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
        created_at=now,
        updated_at=now,
    )
    delivery = PendingDelivery(
        message=TaskMessage(
            task_id=task.task_id,
            workflow_id=_WORKFLOW_ID,
            task_type=TaskType.COLLECT,
            attempt=1,
            created_at=now,
            payload_reference="ref://pl-1",
        ),
        stream="cartoon:tasks",
        consumer_group="workers",
        delivery_id="del-1",
        dequeued_at=now,
    )
    version = resolve_logical_version(
        task_type=TaskType.COLLECT,
        task_record=task,
        delivery=delivery,
        artifact_repo=object(),  # type: ignore[arg-type]
    )
    assert version == 1
