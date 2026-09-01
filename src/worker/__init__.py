"""Worker module public surface."""

from __future__ import annotations

from .errors import (
    DuplicateHandlerError,
    HandlerNotFoundError,
    IdempotencyConflictError,
    LeaseConflictError,
    RetryExhaustedError,
    TaskExecutionError,
    TaskRecordNotFoundError,
    WorkerError,
    WorkerShutdownError,
)
from .protocols import (
    IdempotencyOrchestrator,
    TaskHandler,
    TaskHandlerRegistry,
    WorkerLoop,
    create_idempotency_orchestrator,
    create_task_handler_registry,
    create_worker_loop,
    run_task_loop,
)
from .production import (
    WorkerProductionDependencies,
    create_production_worker_dependencies,
)
from .types import (
    DuplicateResolution,
    IdempotencyCheckResult,
    IdempotencyClaimResult,
    IdempotencyPhase,
    TaskExecutionContext,
    TaskHandlerOutcome,
    TaskHandlerResult,
    TaskTiming,
    WorkerLoopConfig,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "DuplicateHandlerError",
    "DuplicateResolution",
    "HandlerNotFoundError",
    "IdempotencyCheckResult",
    "IdempotencyClaimResult",
    "IdempotencyConflictError",
    "IdempotencyOrchestrator",
    "IdempotencyPhase",
    "LeaseConflictError",
    "RetryExhaustedError",
    "TaskExecutionContext",
    "TaskExecutionError",
    "TaskHandler",
    "TaskHandlerOutcome",
    "TaskHandlerRegistry",
    "TaskHandlerResult",
    "TaskRecordNotFoundError",
    "TaskTiming",
    "WorkerError",
    "WorkerLoop",
    "WorkerLoopConfig",
    "WorkerProductionDependencies",
    "WorkerShutdownError",
    "create_idempotency_orchestrator",
    "create_production_worker_dependencies",
    "create_task_handler_registry",
    "create_worker_loop",
    "run_task_loop",
]
