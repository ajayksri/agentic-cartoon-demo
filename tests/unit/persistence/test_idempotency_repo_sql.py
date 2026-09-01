"""Pre-code test mold for PERS-008 — PostgresIdempotencyRepo (LLD §3.7)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from persistence import (
    IdempotencyInsertSpec,
    IdempotencyOutcome,
    PersistenceTransactionError,
)


def _insert_spec() -> IdempotencyInsertSpec:
    return IdempotencyInsertSpec(
        idempotency_key="key-1",
        workflow_id="wf-1",
        task_id="task-1",
    )


def test_unique_violation_returns_duplicate_result_not_exception() -> None:
    """UniqueViolation on idempotency_key → DUPLICATE result, no exception (PERS-TC-031)."""
    from persistence.repos.idempotency import PostgresIdempotencyRepo

    repo = PostgresIdempotencyRepo()
    conn = MagicMock()
    existing_row = {
        "idempotency_key": "key-1",
        "workflow_id": "wf-1",
        "task_id": "task-1",
        "completed_at": datetime.now(UTC),
        "result_artifact_id": None,
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_connection", lambda: conn)
        mp.setattr(repo, "_require_active_transaction", lambda _op: None)
        mp.setattr(repo, "_insert_row", MagicMock(side_effect=Exception("unique violation")))
        mp.setattr(repo, "_select_by_key", MagicMock(return_value=existing_row))

        result = repo.try_insert(_insert_spec())

    assert result.outcome == IdempotencyOutcome.DUPLICATE
    assert result.record is not None
    assert result.record.idempotency_key == "key-1"


def test_try_insert_outside_transaction_raises() -> None:
    """try_insert outside active scope → PersistenceTransactionError (§5.2.1)."""
    from persistence.repos.idempotency import PostgresIdempotencyRepo

    repo = PostgresIdempotencyRepo()

    with pytest.raises(PersistenceTransactionError) as exc_info:
        repo.try_insert(_insert_spec())

    assert exc_info.value.code == "PERS_TX"
