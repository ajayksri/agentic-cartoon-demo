"""Runtime module public surface — product composition root."""

from __future__ import annotations

from .errors import (
    BootstrapError,
    DependencyWiringError,
    ProcessShutdownError,
    ProcessStartupError,
    RuntimeModuleError,
    UnsupportedProcessKindError,
)
from .protocols import (
    CompositionRoot,
    OutboxPublisherLoop,
    create_composition_root,
    create_outbox_publisher_loop,
    run_api_process,
    run_coordinator_process,
    run_worker_process,
)
from .types import (
    API_ENTRY,
    COORDINATOR_ENTRY,
    WORKER_ENTRY,
    BootstrapResult,
    CoordinatorLoopConfig,
    OutboxPublishBatchResult,
    OutboxPublisherConfig,
    ProcessEntryPoint,
    ProcessKind,
    WiredDependencies,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "API_ENTRY",
    "COORDINATOR_ENTRY",
    "WORKER_ENTRY",
    "BootstrapError",
    "BootstrapResult",
    "CompositionRoot",
    "CoordinatorLoopConfig",
    "DependencyWiringError",
    "OutboxPublishBatchResult",
    "OutboxPublisherConfig",
    "OutboxPublisherLoop",
    "ProcessEntryPoint",
    "ProcessKind",
    "ProcessShutdownError",
    "ProcessStartupError",
    "RuntimeModuleError",
    "UnsupportedProcessKindError",
    "WiredDependencies",
    "create_composition_root",
    "create_outbox_publisher_loop",
    "run_api_process",
    "run_coordinator_process",
    "run_worker_process",
]
