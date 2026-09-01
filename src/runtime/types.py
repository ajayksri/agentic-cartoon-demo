"""Public runtime value types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from config.types import AppConfig

if TYPE_CHECKING:
    from task_queue.protocols import TaskQueue
    from worker.protocols import WorkerLoop
    from workflow.protocols import WorkflowEngine

    from .protocols import OutboxPublisherLoop


class ProcessKind(StrEnum):
    """Long-running V1 process entry kinds (runtime-topology.md §1)."""

    API = "api"
    COORDINATOR = "coordinator"
    WORKER = "worker"


@dataclass(frozen=True, slots=True)
class ProcessEntryPoint:
    """Identifies a long-running process bootstrap target."""

    kind: ProcessKind
    service_name: str
    """OTel/log service identity for this process (MOD-RT-INV-029)."""


API_ENTRY = ProcessEntryPoint(kind=ProcessKind.API, service_name="cartoon-demo-api")
COORDINATOR_ENTRY = ProcessEntryPoint(
    kind=ProcessKind.COORDINATOR,
    service_name="cartoon-demo-coordinator",
)
WORKER_ENTRY = ProcessEntryPoint(kind=ProcessKind.WORKER, service_name="cartoon-demo-worker")


@dataclass(frozen=True, slots=True)
class OutboxPublisherConfig:
    """Tuning for coordinator outbox → queue publish loop."""

    batch_size: int = 100
    poll_interval_seconds: float = 1.0
    shutdown_grace_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class CoordinatorLoopConfig:
    """Combined coordinator background loop settings (CG-RT-006, CG-RT-009)."""

    outbox: OutboxPublisherConfig = field(default_factory=OutboxPublisherConfig)
    reconciliation_interval_seconds: float = 60.0
    reconciliation_batch_size: int = 100


@dataclass(frozen=True, slots=True)
class OutboxPublishBatchResult:
    """Summary of one outbox publisher iteration."""

    fetched_count: int
    published_count: int
    failed_count: int
    skipped_count: int = 0


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Outcome of CompositionRoot.bootstrap for one process entry."""

    entry: ProcessEntryPoint
    config_loaded: bool
    observability_configured: bool
    failure_injection_configured: bool
    message: str | None = None
    """Optional human-readable bootstrap summary for logs."""


@dataclass(frozen=True, slots=True)
class WiredDependencies:
    """Snapshot of primary collaborators after bootstrap (CG-RT-001)."""

    entry: ProcessEntryPoint
    config: AppConfig
    workflow_engine: WorkflowEngine | None = None
    task_queue: TaskQueue | None = None
    api_router: object | None = None
    """Framework-specific router from api.create_api_router."""
    outbox_publisher: OutboxPublisherLoop | None = None
    worker_loop: WorkerLoop | None = None
