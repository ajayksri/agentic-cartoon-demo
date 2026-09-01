"""Pre-code test mold for PERS-009 — PostgresOutboxRepo (LLD §3.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from persistence import OutboxStatus, PersistenceTransactionError


def test_mark_published_idempotent_when_already_published() -> None:
    """Second mark_published on PUBLISHED row succeeds without error (PERS-TC-051)."""
    from persistence.repos.outbox import PostgresOutboxRepo

    repo = PostgresOutboxRepo()
    published_at = datetime.now(UTC)
    entry = MagicMock()
    entry.outbox_id = "ob-1"
    entry.status = OutboxStatus.PUBLISHED
    entry.published_at = published_at

    with pytest.MonkeyPatch.context() as mp:
        update_mock = MagicMock()
        mp.setattr(repo, "_fetch_entry", MagicMock(return_value=entry))
        mp.setattr(repo, "_update_published", update_mock)

        result = repo.mark_published("ob-1", published_at=published_at)

        assert result.status == OutboxStatus.PUBLISHED
        update_mock.assert_not_called()


def test_insert_outside_transaction_raises() -> None:
    """insert outside active scope → PersistenceTransactionError (§5.2.1)."""
    from persistence import OutboxInsertSpec, PayloadReference, TaskType
    from persistence.repos.outbox import PostgresOutboxRepo

    repo = PostgresOutboxRepo()
    spec = OutboxInsertSpec(
        workflow_id="wf-1",
        task_id="task-1",
        task_type=TaskType.COLLECT,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
    )

    with pytest.raises(PersistenceTransactionError) as exc_info:
        repo.insert(spec)

    assert exc_info.value.code == "PERS_TX"
