"""Pre-code test mold for PERS-006 — PostgresWorkflowRepo (LLD §3.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from persistence import (
    PersistenceConflictError,
    PersistenceNotFoundError,
    PersistenceTransactionError,
    WorkflowState,
    WorkflowTransitionRecord,
)


def _transition() -> WorkflowTransitionRecord:
    now = datetime.now(UTC)
    return WorkflowTransitionRecord(
        transition_id="tr-1",
        workflow_id="wf-1",
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COLLECTING,
        reason="start",
        occurred_at=now,
    )


def test_update_workflow_state_rowcount_zero_existing_raises_conflict() -> None:
    """Optimistic UPDATE rowcount 0 when row exists → PersistenceConflictError."""
    from persistence.repos.workflow import PostgresWorkflowRepo

    repo = PostgresWorkflowRepo()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 0
    conn.execute.return_value = cursor

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_connection", lambda: conn)
        mp.setattr(repo, "_workflow_exists", lambda _wf_id: True)
        mp.setattr(repo, "_require_active_transaction", lambda _op: None)

        with pytest.raises(PersistenceConflictError):
            repo.update_workflow_state(
                "wf-1",
                expected_version=2,
                new_state=WorkflowState.COLLECTING,
            )


def test_update_workflow_state_rowcount_zero_missing_raises_not_found() -> None:
    """Optimistic UPDATE rowcount 0 when row missing → PersistenceNotFoundError."""
    from persistence.repos.workflow import PostgresWorkflowRepo

    repo = PostgresWorkflowRepo()
    conn = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 0
    conn.execute.return_value = cursor

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_connection", lambda: conn)
        mp.setattr(repo, "_workflow_exists", lambda _wf_id: False)
        mp.setattr(repo, "_require_active_transaction", lambda _op: None)

        with pytest.raises(PersistenceNotFoundError):
            repo.update_workflow_state(
                "wf-missing",
                expected_version=1,
                new_state=WorkflowState.COLLECTING,
            )


def test_append_transition_outside_transaction_raises() -> None:
    """append_transition outside active scope → PersistenceTransactionError (§5.2.1)."""
    from persistence.repos.workflow import PostgresWorkflowRepo

    repo = PostgresWorkflowRepo()

    with pytest.raises(PersistenceTransactionError) as exc_info:
        repo.append_transition(_transition())

    assert exc_info.value.code == "PERS_TX"
