"""Public type definitions for the worker module contract boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from config.types import AgentId, AppConfig, TaskType
from persistence.types import IdempotencyInsertSpec, IdempotencyRecord, TaskRecord
from task_queue.types import PendingDelivery
from workflow.types import TransitionSignal

if TYPE_CHECKING:
    from agents.protocols import (
        CriticAgent,
        ScenarioGenerationAgent,
        TopicSelectionAgent,
    )
    from collector.protocols import Collector
    from failure_injection.protocols import FailureInjectionRegistry
    from observability.protocols import Logger, Meter, Tracer
    from persistence.protocols import (
        ArtifactRepo,
        TransactionManager,
        WorkflowRepo,
    )
    from providers.protocols import ModelProvider
    from workflow.protocols import WorkflowEngine

    from .protocols import IdempotencyOrchestrator


class TaskHandlerOutcome(StrEnum):
    """Handler-level outcome before loop retry/transition decisions."""

    COMPLETED = "completed"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    DUPLICATE_REUSED = "duplicate_reused"


class DuplicateResolution(StrEnum):
    """How a duplicate task delivery or completion was resolved (ACD-FR-026)."""

    IGNORED_BEFORE_EXECUTION = "ignored_before_execution"
    DETECTED_DURING_EXECUTION = "detected_during_execution"
    REJECTED_DURING_COMMIT = "rejected_during_commit"
    REUSED_COMMITTED_RESULT = "reused_committed_result"


class IdempotencyPhase(StrEnum):
    """Phase of idempotency orchestration."""

    NOT_STARTED = "not_started"
    ALREADY_COMPLETED = "already_completed"
    CLAIMED = "claimed"
    DUPLICATE_REJECTED = "duplicate_rejected"


@dataclass(frozen=True, slots=True)
class TaskTiming:
    """Timing anchors for queue wait and execution duration metrics."""

    enqueued_at: datetime
    dequeued_at: datetime
    handler_started_at: datetime | None = None
    handler_finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TaskExecutionContext:
    """Per-task injected dependencies and delivery metadata (ACD-FR-069)."""

    worker_id: str
    config: AppConfig
    delivery: PendingDelivery
    task_record: TaskRecord
    idempotency_key: str
    timing: TaskTiming
    workflow_engine: WorkflowEngine
    workflow_repo: WorkflowRepo
    artifact_repo: ArtifactRepo
    idempotency_orchestrator: IdempotencyOrchestrator
    transaction_manager: TransactionManager
    failure_injection: FailureInjectionRegistry
    logger: Logger
    meter: Meter
    tracer: Tracer
    collector: Collector
    topic_selection_agent: TopicSelectionAgent
    scenario_generation_agent: ScenarioGenerationAgent
    critic_agent: CriticAgent
    model_provider_factory: Callable[[AgentId], ModelProvider]


@dataclass(frozen=True, slots=True)
class TaskHandlerResult:
    """Outcome returned by TaskHandler.handle for loop orchestration."""

    outcome: TaskHandlerOutcome
    transition_signal: TransitionSignal | None = None
    reason: str | None = None
    result_artifact_id: str | None = None
    duplicate_resolution: DuplicateResolution | None = None
    retryable: bool = False
    error_class: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyCheckResult:
    """Result of pre-execution idempotency lookup."""

    phase: IdempotencyPhase
    idempotency_key: str
    existing_record: IdempotencyRecord | None = None
    duplicate_resolution: DuplicateResolution | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyClaimResult:
    """Result of completion idempotency insert-once claim."""

    phase: IdempotencyPhase
    idempotency_key: str
    record: IdempotencyRecord | None = None
    duplicate_resolution: DuplicateResolution | None = None


@dataclass(frozen=True, slots=True)
class WorkerLoopConfig:
    """Runtime tuning for the worker consume loop."""

    stream: str
    consumer_group: str
    consumer_name: str
    block_ms: int = 5000
    shutdown_grace_seconds: float = 30.0
