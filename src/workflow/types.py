"""Public type definitions for the workflow module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from config.types import TaskType


class WorkflowState(StrEnum):
    """Authoritative V1 workflow states (system-hld.md §5)."""

    CREATED = "CREATED"
    COLLECTING = "COLLECTING"
    COLLECTED = "COLLECTED"
    SELECTING_TOPIC = "SELECTING_TOPIC"
    NO_SUITABLE_TOPIC = "NO_SUITABLE_TOPIC"
    TOPIC_SELECTED = "TOPIC_SELECTED"
    GENERATING_SCENARIO = "GENERATING_SCENARIO"
    SCENARIO_GENERATED = "SCENARIO_GENERATED"
    REVIEWING = "REVIEWING"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REVIEW_PASSED = "REVIEW_PASSED"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVIEW_FAILED = "REVIEW_FAILED"
    FAILED = "FAILED"
    FAILED_PERMANENTLY = "FAILED_PERMANENTLY"


TERMINAL_WORKFLOW_STATES: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.NO_SUITABLE_TOPIC,
        WorkflowState.APPROVED,
        WorkflowState.REJECTED,
        WorkflowState.REVIEW_FAILED,
        WorkflowState.FAILED,
        WorkflowState.FAILED_PERMANENTLY,
    }
)


class ApprovalAction(StrEnum):
    """Human approver actions (workflows.md §7, ACD-FR-014)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_REGENERATION = "REQUEST_REGENERATION"


class TransitionSignal(StrEnum):
    """Completion or failure signal supplied to apply_transition (system-hld.md §7.1)."""

    STAGE_COMPLETED = "stage_completed"
    NO_SUITABLE_TOPIC = "no_suitable_topic"
    CRITIC_REVISE = "critic_revise"
    CRITIC_PASS = "critic_pass"
    UNRECOVERABLE_ERROR = "unrecoverable_error"
    RETRIES_EXHAUSTED = "retries_exhausted"
    RECONCILIATION_REPAIR = "reconciliation_repair"


@dataclass(frozen=True, slots=True)
class InitiateWorkflowRequest:
    """Optional inputs for workflow initiation (CG-WF-001)."""

    workflow_id: str | None = None
    correlation_id: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class OutboxTaskSpec:
    """Task dispatch spec written to transactional outbox (ACD-FR-045, ADR-002)."""

    task_id: str
    workflow_id: str
    task_type: TaskType
    attempt: int
    payload_reference: str
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """Single persisted workflow transition."""

    transition_id: str
    workflow_id: str
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    occurred_at: datetime
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    """Command to apply a workflow transition after stage completion or repair."""

    workflow_id: str
    expected_state: WorkflowState
    signal: TransitionSignal
    reason: str
    actor: str | None = None
    completing_task_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Outcome of a successful apply_transition call."""

    workflow_id: str
    from_state: WorkflowState
    to_state: WorkflowState
    state_version: int
    transition_id: str
    transition: TransitionRecord
    outbox_written: bool
    enqueued_task: OutboxTaskSpec | None = None


@dataclass(frozen=True, slots=True)
class InitiateWorkflowResult:
    """Outcome of initiate_workflow."""

    workflow_id: str
    state: WorkflowState
    state_version: int
    transition: TransitionRecord
    enqueued_task: OutboxTaskSpec


@dataclass(frozen=True, slots=True)
class ApprovalActionResult:
    """Outcome of apply_approval_action."""

    workflow_id: str
    action: ApprovalAction
    from_state: WorkflowState
    to_state: WorkflowState
    state_version: int
    transition_id: str
    transition: TransitionRecord
    enqueued_task: OutboxTaskSpec | None = None


@dataclass(frozen=True, slots=True)
class WorkflowStatus:
    """Current workflow snapshot for status queries."""

    workflow_id: str
    state: WorkflowState
    state_version: int
    created_at: datetime
    updated_at: datetime
    revision_count: int = 0
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowHistory:
    """Append-only transition history."""

    workflow_id: str
    transitions: tuple[TransitionRecord, ...]


@dataclass(frozen=True, slots=True)
class WorkflowOutput:
    """Aggregated output package (ACD-ART-007, ACD-FR-039)."""

    workflow_id: str
    state: WorkflowState
    package: Mapping[str, object]
    is_complete: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """Single human-readable timeline entry (ACD-FR-066)."""

    occurred_at: datetime
    event_type: str
    summary: str
    state: WorkflowState | None = None
    task_type: TaskType | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowTimeline:
    """Ordered timeline for operator inspection."""

    workflow_id: str
    events: tuple[TimelineEvent, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Per-workflow reconciliation outcome."""

    workflow_id: str
    repair_action: str
    repaired: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Batch outcome of reconcile_stuck_workflows."""

    scanned_count: int
    repaired_count: int
    reports: tuple[ReconciliationReport, ...]
