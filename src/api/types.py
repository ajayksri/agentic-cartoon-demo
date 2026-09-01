"""Public REST DTO types for the API module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from config.types import TaskType
from workflow.types import ApprovalAction, WorkflowState


class HealthStatus(StrEnum):
    """Liveness probe status."""

    OK = "ok"
    NOT_OK = "not_ok"


class ReadinessStatus(StrEnum):
    """Readiness probe aggregate status."""

    READY = "ready"
    NOT_READY = "not_ready"


class DependencyCheckStatus(StrEnum):
    """Single dependency check outcome."""

    OK = "ok"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class InitiateWorkflowApiRequest:
    """REST body for workflow creation (ACD-API-001)."""

    workflow_id: str | None = None
    correlation_id: str | None = None
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class InitiateWorkflowApiResponse:
    """REST response after successful workflow initiation."""

    workflow_id: str
    state: WorkflowState
    state_version: int
    created_at: datetime
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowStatusResponse:
    """REST response for workflow status query (ACD-API-002)."""

    workflow_id: str
    state: WorkflowState
    state_version: int
    created_at: datetime
    updated_at: datetime
    revision_count: int = 0
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TransitionRecordResponse:
    """Single transition in history response."""

    transition_id: str
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    occurred_at: datetime
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowHistoryResponse:
    """REST response for workflow history (ACD-API-003)."""

    workflow_id: str
    transitions: tuple[TransitionRecordResponse, ...]


@dataclass(frozen=True, slots=True)
class WorkflowOutputResponse:
    """REST response for workflow output package (ACD-API-004)."""

    workflow_id: str
    state: WorkflowState
    package: Mapping[str, object]
    is_complete: bool
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitApprovalApiRequest:
    """REST body for human approval action (ACD-API-005, ACD-SEC-006)."""

    action: ApprovalAction
    actor: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitApprovalApiResponse:
    """REST response after successful approval action."""

    workflow_id: str
    action: ApprovalAction
    from_state: WorkflowState
    to_state: WorkflowState
    state_version: int
    transition_id: str


@dataclass(frozen=True, slots=True)
class TimelineEventResponse:
    """Single timeline event in REST response (ACD-API-007)."""

    occurred_at: datetime
    event_type: str
    summary: str
    state: WorkflowState | None = None
    task_type: TaskType | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowTimelineResponse:
    """REST response for workflow timeline."""

    workflow_id: str
    events: tuple[TimelineEventResponse, ...]


@dataclass(frozen=True, slots=True)
class HealthResponse:
    """Liveness probe response (ACD-API-006)."""

    status: HealthStatus
    service_name: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    """Single dependency readiness result."""

    name: str
    status: DependencyCheckStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessResponse:
    """Readiness probe response (ACD-API-006)."""

    status: ReadinessStatus
    checks: tuple[DependencyCheck, ...]
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ApiErrorEnvelope:
    """Consistent JSON error body for all 4xx/5xx responses (ACD-API-008, ACD-INT-008)."""

    error_class: str
    message: str
    retryable: bool | None = None
    workflow_id: str | None = None
    details: Mapping[str, str] | None = None
