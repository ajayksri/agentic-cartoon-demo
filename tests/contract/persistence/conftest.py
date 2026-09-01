"""Contract fixtures for persistence (LLD §8.3, PERS-013)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from persistence import (
    PayloadReference,
    TaskRecord,
    TaskStatus,
    TaskType,
)


@pytest.fixture
def fresh_workflow_id() -> Callable[[], str]:
    """Generate a unique workflow identifier per test."""

    def _factory() -> str:
        return f"wf-{uuid.uuid4()}"

    return _factory


@pytest.fixture
def sample_task_with_payload() -> tuple[TaskRecord, dict[str, object]]:
    """TaskRecord with JSON payload for PERS-TC-005."""
    now = datetime.now(UTC)
    payload = {"headline": "contract-test", "score": 1}
    task = TaskRecord(
        task_id=f"task-{uuid.uuid4()}",
        workflow_id=f"wf-{uuid.uuid4()}",
        task_type=TaskType.COLLECT,
        attempt=1,
        status=TaskStatus.PENDING,
        payload_reference=PayloadReference(ref_id=f"pl-{uuid.uuid4()}", ref_kind="task_payload"),
        idempotency_key=f"idem-{uuid.uuid4()}",
        created_at=now,
        updated_at=now,
    )
    return task, payload


@pytest.fixture
def memory_persistence_bundle():
    """In-memory repos + transaction manager for contract tests (LLD §8.3)."""
    from persistence.fakes.artifact import InMemoryArtifactRepo
    from persistence.fakes.idempotency import InMemoryIdempotencyRepo
    from persistence.fakes.outbox import InMemoryOutboxRepo
    from persistence.fakes.task_lease import InMemoryTaskLeaseRepo
    from persistence.fakes.transaction import InMemoryTransactionManager
    from persistence.fakes.workflow import InMemoryWorkflowRepo

    def _factory(*, clock: Callable[[], datetime] | None = None):
        txn = InMemoryTransactionManager()
        return SimpleNamespace(
            transaction_manager=txn,
            workflow_repo=InMemoryWorkflowRepo(transaction_manager=txn),
            artifact_repo=InMemoryArtifactRepo(transaction_manager=txn),
            idempotency_repo=InMemoryIdempotencyRepo(transaction_manager=txn),
            outbox_repo=InMemoryOutboxRepo(transaction_manager=txn),
            task_lease_repo=InMemoryTaskLeaseRepo(transaction_manager=txn, clock=clock),
        )

    return _factory


def _apply_persistence_migration(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> None:
    import psycopg

    migration_path = (
        Path(__file__).resolve().parents[3] / "migrations" / "persistence" / "001_initial.sql"
    )
    ddl = migration_path.read_text(encoding="utf-8")
    with psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
    ) as conn:
        conn.execute(ddl)
        conn.commit()


@pytest.fixture(scope="session")
def postgres_connection_settings():
    """Resolved ConnectionSettings for optional PostgreSQL contract profile."""
    pytest.importorskip("testcontainers")
    from testcontainers.community.postgres import PostgresContainer

    from persistence.bootstrap import ConnectionSettings

    with PostgresContainer("postgres:16-alpine") as postgres:
        host = postgres.get_container_host_ip()
        port = int(postgres.get_exposed_port(5432))
        database = postgres.dbname
        user = postgres.username
        password = postgres.password
        _apply_persistence_migration(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        yield ConnectionSettings(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_pool_size=1,
            max_pool_size=4,
            connection_timeout_seconds=30.0,
        )


@pytest.fixture
def postgres_persistence_bundle(postgres_connection_settings) -> Iterator[SimpleNamespace]:
    """PostgreSQL bundle via create_persistence_stack (optional PG profile)."""
    from persistence.bootstrap import PersistenceStackOptions, create_persistence_stack

    bundle = create_persistence_stack(
        postgres_connection_settings,
        options=PersistenceStackOptions(health_check_on_bootstrap=True),
    )
    yield bundle
    bundle.pool_manager.close()


@pytest.fixture
def concurrent_try_insert_harness():
    """Threaded barrier harness for PERS-TC-032."""

    def _run(target: Callable[[], object], *, threads: int = 2) -> list[object]:
        barrier = threading.Barrier(threads)
        results: list[object] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def _worker() -> None:
            barrier.wait()
            try:
                outcome = target()
            except BaseException as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)
            else:
                with lock:
                    results.append(outcome)

        workers = [threading.Thread(target=_worker) for _ in range(threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        if errors:
            raise errors[0]
        return results

    return _run
