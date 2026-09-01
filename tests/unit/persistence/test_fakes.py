"""Pre-code test mold for PERS-012 — in-memory fakes (LLD §3.10)."""

from __future__ import annotations

import pytest

from persistence import (
    IdempotencyInsertSpec,
    IdempotencyOutcome,
    PersistenceTransactionError,
    WorkflowState,
)


def test_transaction_rollback_restores_pre_txn_state() -> None:
    """Rollback restores snapshot taken at transaction enter (PERS-TC-052 variant)."""
    from persistence.fakes.transaction import InMemoryTransactionManager
    from persistence.fakes.workflow import InMemoryWorkflowRepo

    txn = InMemoryTransactionManager()
    repo = InMemoryWorkflowRepo(transaction_manager=txn)

    repo.create_workflow("wf-1", initial_state=WorkflowState.CREATED)
    assert repo.get_workflow("wf-1") is not None

    with pytest.raises(RuntimeError, match="abort"):
        with txn.transaction():
            repo.update_workflow_state(
                "wf-1",
                expected_version=1,
                new_state=WorkflowState.COLLECTING,
            )
            raise RuntimeError("abort")

    record = repo.get_workflow("wf-1")
    assert record is not None
    assert record.state == WorkflowState.CREATED


def test_idempotency_duplicate_returns_result_not_exception() -> None:
    """Duplicate idempotency key → DUPLICATE result inside transaction."""
    from persistence.fakes.idempotency import InMemoryIdempotencyRepo
    from persistence.fakes.transaction import InMemoryTransactionManager

    txn = InMemoryTransactionManager()
    repo = InMemoryIdempotencyRepo(transaction_manager=txn)
    spec = IdempotencyInsertSpec(
        idempotency_key="dup-key",
        workflow_id="wf-1",
        task_id="task-1",
    )

    with txn.transaction():
        first = repo.try_insert(spec)
        second = repo.try_insert(spec)

    assert first.outcome == IdempotencyOutcome.INSERTED
    assert second.outcome == IdempotencyOutcome.DUPLICATE


def test_nested_fake_transaction_raises() -> None:
    """Nested InMemoryTransactionManager.transaction() → PersistenceTransactionError."""
    from persistence.fakes.transaction import InMemoryTransactionManager

    txn = InMemoryTransactionManager()

    with txn.transaction():
        with pytest.raises(PersistenceTransactionError):
            with txn.transaction():
                pass
