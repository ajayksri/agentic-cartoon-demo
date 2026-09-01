"""Contract test skeleton for PERS-TC-001 through PERS-TC-080 (PERS-013).

Test modules import ONLY from the public persistence package surface.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from persistence import (
    ArtifactCreateSpec,
    ArtifactType,
    IdempotencyInsertSpec,
    IdempotencyOutcome,
    OutboxInsertSpec,
    OutboxStatus,
    PayloadReference,
    PersistenceConflictError,
    PersistenceNotFoundError,
    TaskStatus,
    TaskType,
    WorkflowState,
    WorkflowTransitionRecord,
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "workflow",
    "worker",
    "agents",
    "api",
    "task_queue",
    "providers",
)


def _src_persistence_root() -> Path:
    return Path(__file__).resolve().parents[3] / "src" / "persistence"


# --- 1. State authority and durability ---


@pytest.mark.pers_tc("001")
def test_pers_tc_001_workflow_state_survives_reconnection(
    postgres_persistence_bundle,
    postgres_connection_settings,
    fresh_workflow_id,
) -> None:
    """PERS-TC-001: Workflow state survives reconnection."""
    from persistence.bootstrap import create_persistence_stack

    wf_id = fresh_workflow_id()
    bundle = postgres_persistence_bundle
    bundle.workflow_repo.create_workflow(wf_id, initial_state=WorkflowState.CREATED)

    bundle.pool_manager.close()
    reopened = create_persistence_stack(postgres_connection_settings)
    try:
        reloaded = reopened.workflow_repo.get_workflow(wf_id)
    finally:
        reopened.pool_manager.close()

    assert reloaded is not None
    assert reloaded.state == WorkflowState.CREATED
    assert reloaded.state_version == 1


@pytest.mark.pers_tc("002")
def test_pers_tc_002_workflow_state_queryable_without_external_context(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-002: Current state and transition history from persistence alone."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id, initial_state=WorkflowState.CREATED)
    now = datetime.now(UTC)
    transition = WorkflowTransitionRecord(
        transition_id="tr-1",
        workflow_id=wf_id,
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COLLECTING,
        reason="start",
        occurred_at=now,
    )
    with bundle.transaction_manager.transaction():
        bundle.workflow_repo.update_workflow_state(
            wf_id, expected_version=1, new_state=WorkflowState.COLLECTING
        )
        bundle.workflow_repo.append_transition(transition)

    workflow = bundle.workflow_repo.get_workflow(wf_id)
    history = bundle.workflow_repo.list_transitions(wf_id)

    assert workflow is not None
    assert workflow.state == WorkflowState.COLLECTING
    assert len(history) == 1


@pytest.mark.pers_tc("003")
def test_pers_tc_003_transitions_are_append_only(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-003: Repository API provides no transition mutation path."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    now = datetime.now(UTC)
    transition = WorkflowTransitionRecord(
        transition_id="tr-1",
        workflow_id=wf_id,
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COLLECTING,
        reason="start",
        occurred_at=now,
    )
    with bundle.transaction_manager.transaction():
        bundle.workflow_repo.append_transition(transition)

    repo = bundle.workflow_repo
    assert not hasattr(repo, "update_transition")
    assert not hasattr(repo, "delete_transition")


# --- 2. Task records ---


@pytest.mark.pers_tc("004")
def test_pers_tc_004_task_envelope_fields_persisted(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-004: Task envelope fields round-trip via create_task/get_task."""
    from persistence import TaskRecord

    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    now = datetime.now(UTC)
    task = TaskRecord(
        task_id="task-1",
        workflow_id=wf_id,
        task_type=TaskType.COLLECT,
        attempt=1,
        status=TaskStatus.PENDING,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
        created_at=now,
        updated_at=now,
    )
    with bundle.transaction_manager.transaction():
        created = bundle.workflow_repo.create_task(task)

    loaded = bundle.workflow_repo.get_task(created.task_id)

    assert loaded is not None
    assert loaded.task_id == task.task_id
    assert loaded.workflow_id == wf_id
    assert loaded.task_type == TaskType.COLLECT
    assert loaded.payload_reference == task.payload_reference


@pytest.mark.pers_tc("005")
def test_pers_tc_005_task_payload_loaded_by_reference(
    memory_persistence_bundle,
    sample_task_with_payload,
) -> None:
    """PERS-TC-005: get_task_payload returns JSON by reference."""
    bundle = memory_persistence_bundle()
    task, payload = sample_task_with_payload
    bundle.workflow_repo.create_workflow(task.workflow_id)
    with bundle.transaction_manager.transaction():
        created = bundle.workflow_repo.create_task(task, payload=payload)

    loaded = bundle.workflow_repo.get_task_payload(created.payload_reference)

    assert loaded == payload


# --- 3. Artifact versioning ---


@pytest.mark.pers_tc("010")
def test_pers_tc_010_create_versioned_artifact_with_jsonb_content(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-010: Artifact metadata and content retrievable."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    spec = ArtifactCreateSpec(
        workflow_id=wf_id,
        artifact_type=ArtifactType.TOPIC_SELECTION,
        name="topic-v1",
        version=1,
        logical_version=1,
        content={"topics": ["a", "b"]},
    )
    with bundle.transaction_manager.transaction():
        record = bundle.artifact_repo.create_artifact(spec)

    content = bundle.artifact_repo.get_artifact_content(record.artifact_id)
    assert content == spec.content


@pytest.mark.pers_tc("011")
def test_pers_tc_011_topic_selection_retrievable_by_workflow_and_version(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-011: Topic selection artifact listed with correct version."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    spec = ArtifactCreateSpec(
        workflow_id=wf_id,
        artifact_type=ArtifactType.TOPIC_SELECTION,
        name="topic-v1",
        version=1,
        logical_version=1,
        content={"topics": ["news"]},
    )
    with bundle.transaction_manager.transaction():
        bundle.artifact_repo.create_artifact(spec)

    listed = bundle.artifact_repo.list_artifacts(
        wf_id, artifact_type=ArtifactType.TOPIC_SELECTION
    )

    assert len(listed) == 1
    assert listed[0].version == 1


@pytest.mark.pers_tc("012")
def test_pers_tc_012_scenario_version_retained_on_regeneration(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-012: Both scenario versions present; v2 active."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    with bundle.transaction_manager.transaction():
        bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.SCENARIO,
                name="scenario-v1",
                version=1,
                logical_version=1,
                content={"v": 1},
                is_active=True,
            )
        )
        bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.SCENARIO,
                name="scenario-v2",
                version=2,
                logical_version=2,
                content={"v": 2},
                is_active=True,
            )
        )

    versions = bundle.artifact_repo.list_artifacts(wf_id, artifact_type=ArtifactType.SCENARIO)
    active = [v for v in versions if v.is_active]

    assert len(versions) == 2
    assert len(active) == 1
    assert active[0].version == 2


@pytest.mark.pers_tc("013")
def test_pers_tc_013_critic_review_artifact_stored(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-013: Active critic review artifact returned."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    with bundle.transaction_manager.transaction():
        bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.CRITIC_REVIEW,
                name="critic-v1",
                version=1,
                logical_version=1,
                content={"status": "PASS"},
            )
        )

    active = bundle.artifact_repo.get_active_artifact(wf_id, ArtifactType.CRITIC_REVIEW)

    assert active is not None
    assert active.artifact_type == ArtifactType.CRITIC_REVIEW


@pytest.mark.pers_tc("014")
def test_pers_tc_014_only_one_active_version_per_artifact_type(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-014: v2 active; v1 inactive; both retrievable."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    with bundle.transaction_manager.transaction():
        v1 = bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.SCENARIO,
                name="scenario-v1",
                version=1,
                logical_version=1,
                content={"v": 1},
                is_active=True,
            )
        )
        v2 = bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.SCENARIO,
                name="scenario-v2",
                version=2,
                logical_version=2,
                content={"v": 2},
                is_active=True,
            )
        )

    refreshed_v1 = bundle.artifact_repo.get_artifact(v1.artifact_id)

    assert v2.is_active is True
    assert refreshed_v1 is not None
    assert refreshed_v1.is_active is False


@pytest.mark.pers_tc("015")
def test_pers_tc_015_committed_artifact_content_immutable(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-015: No in-place content mutation API."""
    bundle = memory_persistence_bundle()
    repo = bundle.artifact_repo
    assert not hasattr(repo, "update_artifact_content")
    assert not hasattr(repo, "mutate_artifact_content")


@pytest.mark.pers_tc("016")
def test_pers_tc_016_prompt_response_artifact_stored_by_id(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-016: PROMPT_RESPONSE artifact retrievable by artifact_id."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    with bundle.transaction_manager.transaction():
        record = bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.PROMPT_RESPONSE,
                name="prompt-v1",
                version=1,
                logical_version=1,
                content={"prompt": "hello"},
            )
        )

    loaded = bundle.artifact_repo.get_artifact(record.artifact_id)

    assert loaded is not None
    assert loaded.artifact_id == record.artifact_id


@pytest.mark.pers_tc("017")
def test_pers_tc_017_data_available_for_output_package_assembly(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-017: Sufficient records for upstream read model."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id, initial_state=WorkflowState.REVIEW_PASSED)
    with bundle.transaction_manager.transaction():
        bundle.artifact_repo.create_artifact(
            ArtifactCreateSpec(
                workflow_id=wf_id,
                artifact_type=ArtifactType.TOPIC_SELECTION,
                name="topic",
                version=1,
                logical_version=1,
                content={"topics": ["t"]},
            )
        )

    assert bundle.workflow_repo.get_workflow(wf_id) is not None
    assert bundle.artifact_repo.list_artifacts(wf_id)


@pytest.mark.pers_tc("018")
def test_pers_tc_018_ai_invocation_audit_append_only(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-018: AI invocation append-only audit records."""
    from persistence import AiInvocationInsertSpec, InvocationStatus

    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    now = datetime.now(UTC)
    spec = AiInvocationInsertSpec(
        workflow_id=wf_id,
        task_id="task-1",
        agent_name="topic_selector",
        agent_version="1",
        prompt_version="1",
        provider="openai",
        model="gpt-4",
        input_artifact_id=None,
        output_artifact_id=None,
        attempt=1,
        started_at=now,
        completed_at=now,
        status=InvocationStatus.SUCCESS,
    )
    bundle.artifact_repo.append_ai_invocation(spec)

    records = bundle.artifact_repo.list_ai_invocations(wf_id)

    assert len(records) == 1
    assert records[0].agent_name == "topic_selector"


# --- 4. Idempotency ---


@pytest.mark.pers_tc("030")
def test_pers_tc_030_first_idempotency_insert_succeeds(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-030: Fresh key returns INSERTED."""
    bundle = memory_persistence_bundle()
    spec = IdempotencyInsertSpec(
        idempotency_key="key-new",
        workflow_id=fresh_workflow_id(),
        task_id="task-1",
    )
    with bundle.transaction_manager.transaction():
        result = bundle.idempotency_repo.try_insert(spec)

    assert result.outcome == IdempotencyOutcome.INSERTED
    assert result.record is not None


@pytest.mark.pers_tc("031")
def test_pers_tc_031_duplicate_idempotency_insert_detected(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-031: Duplicate key returns DUPLICATE without second row."""
    bundle = memory_persistence_bundle()
    spec = IdempotencyInsertSpec(
        idempotency_key="key-dup",
        workflow_id=fresh_workflow_id(),
        task_id="task-1",
    )
    with bundle.transaction_manager.transaction():
        bundle.idempotency_repo.try_insert(spec)
        result = bundle.idempotency_repo.try_insert(spec)

    assert result.outcome == IdempotencyOutcome.DUPLICATE


@pytest.mark.pers_tc("032")
def test_pers_tc_032_concurrent_duplicate_insert_exactly_one_wins(
    postgres_persistence_bundle,
    concurrent_try_insert_harness,
    fresh_workflow_id,
) -> None:
    """PERS-TC-032: Concurrent try_insert — exactly one INSERTED."""
    bundle = postgres_persistence_bundle
    wf_id = fresh_workflow_id()
    spec = IdempotencyInsertSpec(
        idempotency_key="key-race",
        workflow_id=wf_id,
        task_id="task-1",
    )

    def _attempt():
        with bundle.transaction_manager.transaction():
            return bundle.idempotency_repo.try_insert(spec)

    outcomes = concurrent_try_insert_harness(_attempt, threads=2)
    inserted = [o for o in outcomes if o.outcome == IdempotencyOutcome.INSERTED]
    duplicate = [o for o in outcomes if o.outcome == IdempotencyOutcome.DUPLICATE]

    assert len(inserted) == 1
    assert len(duplicate) == 1


@pytest.mark.pers_tc("033")
def test_pers_tc_033_idempotency_lookup_by_key(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-033: get_by_key returns matching record."""
    bundle = memory_persistence_bundle()
    spec = IdempotencyInsertSpec(
        idempotency_key="key-lookup",
        workflow_id=fresh_workflow_id(),
        task_id="task-1",
    )
    with bundle.transaction_manager.transaction():
        bundle.idempotency_repo.try_insert(spec)

    record = bundle.idempotency_repo.get_by_key("key-lookup")

    assert record is not None
    assert record.idempotency_key == "key-lookup"


# --- 5. Task leases ---


@pytest.mark.pers_tc("040")
def test_pers_tc_040_acquire_and_release_lease(memory_persistence_bundle) -> None:
    """PERS-TC-040: Lease created then removed; re-acquire succeeds."""
    bundle = memory_persistence_bundle()
    lease = bundle.task_lease_repo.try_acquire("task-1", worker_id="w1", ttl_seconds=60.0)
    assert lease is not None
    bundle.task_lease_repo.release(lease.lease_id)
    again = bundle.task_lease_repo.try_acquire("task-1", worker_id="w2", ttl_seconds=60.0)
    assert again is not None


@pytest.mark.pers_tc("041")
def test_pers_tc_041_second_worker_blocked_by_active_lease(
    memory_persistence_bundle,
) -> None:
    """PERS-TC-041: Second try_acquire returns None while lease active."""
    bundle = memory_persistence_bundle()
    first = bundle.task_lease_repo.try_acquire("task-1", worker_id="w1", ttl_seconds=60.0)
    second = bundle.task_lease_repo.try_acquire("task-1", worker_id="w2", ttl_seconds=60.0)

    assert first is not None
    assert second is None


@pytest.mark.pers_tc("042")
def test_pers_tc_042_expired_lease_allows_reacquire(memory_persistence_bundle) -> None:
    """PERS-TC-042: Expired lease allows new acquire with injected clock."""
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    expired = start + timedelta(seconds=120)
    # try_acquire calls clock for expiry check and acquired_at on the second acquire.
    times = iter([start, expired, expired])

    bundle = memory_persistence_bundle(clock=lambda: next(times))
    first = bundle.task_lease_repo.try_acquire("task-1", worker_id="w1", ttl_seconds=30.0)
    second = bundle.task_lease_repo.try_acquire("task-1", worker_id="w2", ttl_seconds=30.0)

    assert first is not None
    assert second is not None


# --- 6. Transactional outbox ---


@pytest.mark.pers_tc("050")
def test_pers_tc_050_outbox_insert_and_fetch_unpublished(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-050: Unpublished outbox row returned by fetch_unpublished."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    spec = OutboxInsertSpec(
        workflow_id=wf_id,
        task_id="task-1",
        task_type=TaskType.COLLECT,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
    )
    with bundle.transaction_manager.transaction():
        bundle.outbox_repo.insert(spec)

    rows = bundle.outbox_repo.fetch_unpublished(limit=10)

    assert len(rows) >= 1
    assert rows[0].status == OutboxStatus.PENDING


@pytest.mark.pers_tc("051")
def test_pers_tc_051_mark_published_idempotent(memory_persistence_bundle) -> None:
    """PERS-TC-051: Second mark_published is idempotent."""
    bundle = memory_persistence_bundle()
    published_at = datetime.now(UTC)
    with bundle.transaction_manager.transaction():
        entry = bundle.outbox_repo.insert(
            OutboxInsertSpec(
                workflow_id="wf-1",
                task_id="task-1",
                task_type=TaskType.COLLECT,
                payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
                idempotency_key="idem-1",
            )
        )
    first = bundle.outbox_repo.mark_published(entry.outbox_id, published_at=published_at)
    second = bundle.outbox_repo.mark_published(entry.outbox_id, published_at=published_at)

    assert first.status == OutboxStatus.PUBLISHED
    assert second.status == OutboxStatus.PUBLISHED


@pytest.mark.pers_tc("052")
def test_pers_tc_052_atomic_state_and_outbox_commit(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-052: State + outbox visible after commit; none after rollback."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id, initial_state=WorkflowState.CREATED)
    outbox_spec = OutboxInsertSpec(
        workflow_id=wf_id,
        task_id="task-1",
        task_type=TaskType.COLLECT,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-atomic",
    )

    with bundle.transaction_manager.transaction():
        bundle.workflow_repo.update_workflow_state(
            wf_id, expected_version=1, new_state=WorkflowState.COLLECTING
        )
        bundle.outbox_repo.insert(outbox_spec)

    workflow = bundle.workflow_repo.get_workflow(wf_id)
    pending = bundle.outbox_repo.fetch_unpublished(limit=10)

    assert workflow is not None
    assert workflow.state == WorkflowState.COLLECTING
    assert any(row.idempotency_key == "idem-atomic" for row in pending)

    bundle.workflow_repo.create_workflow(fresh_workflow_id(), initial_state=WorkflowState.CREATED)
    rollback_wf = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(rollback_wf, initial_state=WorkflowState.CREATED)
    with pytest.raises(RuntimeError, match="rollback"):
        with bundle.transaction_manager.transaction():
            bundle.workflow_repo.update_workflow_state(
                rollback_wf, expected_version=1, new_state=WorkflowState.COLLECTING
            )
            bundle.outbox_repo.insert(
                OutboxInsertSpec(
                    workflow_id=rollback_wf,
                    task_id="task-rollback",
                    task_type=TaskType.COLLECT,
                    payload_reference=PayloadReference(ref_id="pl-rb", ref_kind="task_payload"),
                    idempotency_key="idem-rollback",
                )
            )
            raise RuntimeError("rollback")

    rolled_back = bundle.workflow_repo.get_workflow(rollback_wf)
    assert rolled_back is not None
    assert rolled_back.state == WorkflowState.CREATED
    assert not any(row.idempotency_key == "idem-rollback" for row in bundle.outbox_repo.fetch_unpublished(10))


# --- 7. Optimistic concurrency ---


@pytest.mark.pers_tc("060")
def test_pers_tc_060_workflow_state_version_conflict(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-060: Stale expected_version → PersistenceConflictError; state unchanged."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id, initial_state=WorkflowState.CREATED)

    with bundle.transaction_manager.transaction():
        bundle.workflow_repo.update_workflow_state(
            wf_id, expected_version=1, new_state=WorkflowState.COLLECTING
        )

    with pytest.raises(PersistenceConflictError):
        with bundle.transaction_manager.transaction():
            bundle.workflow_repo.update_workflow_state(
                wf_id, expected_version=1, new_state=WorkflowState.COLLECTED
            )

    workflow = bundle.workflow_repo.get_workflow(wf_id)
    assert workflow is not None
    assert workflow.state == WorkflowState.COLLECTING
    assert workflow.state_version == 2


# --- 8. Error and security boundaries ---


@pytest.mark.pers_tc("070")
def test_pers_tc_070_not_found_error(memory_persistence_bundle) -> None:
    """PERS-TC-070: Update on missing workflow raises PersistenceNotFoundError."""
    bundle = memory_persistence_bundle()

    with pytest.raises(PersistenceNotFoundError):
        with bundle.transaction_manager.transaction():
            bundle.workflow_repo.update_workflow_state(
                "wf-does-not-exist",
                expected_version=1,
                new_state=WorkflowState.COLLECTING,
            )


@pytest.mark.pers_tc("071")
def test_pers_tc_071_errors_omit_secrets_and_artifact_content(
    memory_persistence_bundle,
    fresh_workflow_id,
) -> None:
    """PERS-TC-071: Exception messages omit secrets and raw JSONB."""
    bundle = memory_persistence_bundle()
    wf_id = fresh_workflow_id()
    bundle.workflow_repo.create_workflow(wf_id)
    sensitive = '{"api_key":"sk-live-secret","password":"hunter2"}'

    try:
        with bundle.transaction_manager.transaction():
            bundle.artifact_repo.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=wf_id,
                    artifact_type=ArtifactType.PROMPT_RESPONSE,
                    name="secret-artifact",
                    version=1,
                    logical_version=1,
                    content={"body": sensitive},
                )
            )
            bundle.workflow_repo.update_workflow_state(
                "wf-missing",
                expected_version=99,
                new_state=WorkflowState.FAILED,
            )
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        assert "sk-live" not in message
        assert "hunter2" not in message
        assert "api_key" not in message
    else:
        pytest.fail("expected PersistenceNotFoundError or similar")


# --- 9. Module boundary ---


@pytest.mark.pers_tc("080")
def test_pers_tc_080_forbidden_dependency_imports_absent() -> None:
    """PERS-TC-080: No imports from forbidden modules in src/persistence/."""
    root = _src_persistence_root()
    violations: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in _FORBIDDEN_IMPORT_PREFIXES:
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in _FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(f"{path}: from {node.module}")

    assert violations == []
