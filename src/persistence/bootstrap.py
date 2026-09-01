"""Resolved DSN components and persistence stack bootstrap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from persistence.errors import PersistenceConnectionError
from persistence.events import MetricsRecorder, OperationLogger
from persistence.protocols import (
    ArtifactRepo,
    IdempotencyRepo,
    OutboxRepo,
    TaskLeaseRepo,
    TransactionManager,
    WorkflowRepo,
)

if TYPE_CHECKING:
    from persistence.pool import ConnectionPoolManager


@dataclass(frozen=True, slots=True)
class ConnectionSettings:
    """Resolved DSN components — no env var names, no secrets in repr."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    min_pool_size: int = 1
    max_pool_size: int = 10
    connection_timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class PersistenceBundle:
    transaction_manager: TransactionManager
    workflow_repo: WorkflowRepo
    artifact_repo: ArtifactRepo
    idempotency_repo: IdempotencyRepo
    outbox_repo: OutboxRepo
    task_lease_repo: TaskLeaseRepo
    pool_manager: ConnectionPoolManager


@dataclass(frozen=True, slots=True)
class PersistenceStackOptions:
    """Optional bootstrap tuning — not part of public contract."""

    operation_logger: OperationLogger | None = None
    metrics_recorder: MetricsRecorder | None = None
    health_check_on_bootstrap: bool = True
    clock: Callable[[], datetime] | None = None


def create_persistence_stack(
    settings: ConnectionSettings,
    *,
    options: PersistenceStackOptions | None = None,
) -> PersistenceBundle:
    """Build pool, transaction manager, and all PostgreSQL repository implementations."""
    from persistence.events import NoOpMetricsRecorder, NoOpOperationLogger
    from persistence.pool import ConnectionPoolManager
    from persistence.repos.artifact import PostgresArtifactRepo
    from persistence.repos.idempotency import PostgresIdempotencyRepo
    from persistence.repos.outbox import PostgresOutboxRepo
    from persistence.repos.task_lease import PostgresTaskLeaseRepo
    from persistence.repos.workflow import PostgresWorkflowRepo
    from persistence.transaction import PostgresTransactionManager

    opts = options or PersistenceStackOptions()
    pool_manager = ConnectionPoolManager(settings)

    if opts.health_check_on_bootstrap:
        try:
            pool_manager.health_check()
        except PersistenceConnectionError:
            raise
        except Exception as exc:
            raise PersistenceConnectionError(
                "Persistence connection error during health_check"
            ) from exc

    operation_logger = opts.operation_logger or NoOpOperationLogger()
    metrics_recorder = opts.metrics_recorder or NoOpMetricsRecorder()
    repo_kwargs = {
        "operation_logger": operation_logger,
        "metrics_recorder": metrics_recorder,
    }

    transaction_manager = PostgresTransactionManager(pool_manager)
    workflow_repo = PostgresWorkflowRepo(pool_manager, **repo_kwargs)
    artifact_repo = PostgresArtifactRepo(pool_manager, **repo_kwargs)
    idempotency_repo = PostgresIdempotencyRepo(pool_manager, **repo_kwargs)
    outbox_repo = PostgresOutboxRepo(pool_manager, **repo_kwargs)
    task_lease_repo = PostgresTaskLeaseRepo(
        pool_manager,
        clock=opts.clock,
        **repo_kwargs,
    )

    return PersistenceBundle(
        transaction_manager=transaction_manager,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_repo=idempotency_repo,
        outbox_repo=outbox_repo,
        task_lease_repo=task_lease_repo,
        pool_manager=pool_manager,
    )
