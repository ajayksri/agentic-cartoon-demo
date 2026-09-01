"""Pre-code test mold for PERS-005 — RowMapper and SQL fragments (LLD §3.3)."""

from __future__ import annotations

import pytest

from persistence import ArtifactType, PersistenceValidationError, TaskType, WorkflowState


def test_unknown_workflow_state_token_raises_validation_error() -> None:
    """Unknown enum token on read → PersistenceValidationError (MOD-PERS-INV-017a)."""
    from persistence.repos._mappers import RowMapper

    mapper = RowMapper()

    with pytest.raises(PersistenceValidationError) as exc_info:
        mapper.workflow_state_from_db("NOT_A_REAL_STATE")

    assert exc_info.value.code == "PERS_VALIDATION"


def test_workflow_state_enum_round_trip_all_members() -> None:
    """All WorkflowState members round-trip through RowMapper."""
    from persistence.repos._mappers import RowMapper

    mapper = RowMapper()

    for member in WorkflowState:
        token = mapper.workflow_state_to_db(member)
        assert mapper.workflow_state_from_db(token) is member


def test_task_type_enum_round_trip_all_members() -> None:
    """All TaskType members round-trip through RowMapper."""
    from persistence.repos._mappers import RowMapper

    mapper = RowMapper()

    for member in TaskType:
        token = mapper.task_type_to_db(member)
        assert mapper.task_type_from_db(token) is member


def test_artifact_type_enum_round_trip_all_members() -> None:
    """All ArtifactType members round-trip through RowMapper."""
    from persistence.repos._mappers import RowMapper

    mapper = RowMapper()

    for member in ArtifactType:
        token = mapper.artifact_type_to_db(member)
        assert mapper.artifact_type_from_db(token) is member


def test_sql_fragments_are_parameterized() -> None:
    """_sql.py defines non-empty parameterized fragments for LLD §4.2 tables."""
    from persistence.repos import _sql

    expected_tables = (
        "WORKFLOWS",
        "WORKFLOW_TRANSITIONS",
        "TASK_PAYLOADS",
        "TASKS",
        "ARTIFACTS",
        "ARTIFACT_CONTENT",
        "IDEMPOTENCY",
        "OUTBOX",
        "TASK_LEASES",
        "AI_INVOCATIONS",
    )
    for name in expected_tables:
        fragment = getattr(_sql, name, None)
        assert fragment is not None, f"missing SQL fragment for {name}"
        assert "%" in fragment or "$" in fragment
