"""Pre-code test mold for PERS-007 — PostgresArtifactRepo (LLD §3.6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from persistence import ArtifactCreateSpec, ArtifactType, PersistenceTransactionError


def _active_artifact_spec() -> ArtifactCreateSpec:
    return ArtifactCreateSpec(
        workflow_id="wf-1",
        artifact_type=ArtifactType.SCENARIO,
        name="scenario-v2",
        version=2,
        logical_version=2,
        content={"scene": "test"},
        is_active=True,
    )


def test_create_active_artifact_outside_transaction_raises() -> None:
    """create_artifact(is_active=True) outside txn → PersistenceTransactionError."""
    from persistence.repos.artifact import PostgresArtifactRepo

    repo = PostgresArtifactRepo()

    with pytest.raises(PersistenceTransactionError) as exc_info:
        repo.create_artifact(_active_artifact_spec())

    assert exc_info.value.code == "PERS_TX"


def test_active_flag_swap_executes_deactivate_and_insert() -> None:
    """Active artifact create issues deactivate UPDATE then INSERT pair (PERS-TC-014)."""
    from persistence.repos.artifact import PostgresArtifactRepo

    repo = PostgresArtifactRepo()
    conn = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "_connection", lambda: conn)
        mp.setattr(repo, "_require_active_transaction", lambda _op: None)

        repo.create_artifact(_active_artifact_spec())

    assert conn.execute.call_count >= 2
    statements = [str(c.args[0]).upper() for c in conn.execute.call_args_list]
    assert any("UPDATE" in stmt and "IS_ACTIVE" in stmt for stmt in statements)
    assert any("INSERT" in stmt for stmt in statements)
