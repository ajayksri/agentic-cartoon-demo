"""Public persistence value types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


class WorkflowState(StrEnum):
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


class TaskType(StrEnum):
    COLLECT = "COLLECT"
    SELECT_TOPIC = "SELECT_TOPIC"
    GENERATE_SCENARIO = "GENERATE_SCENARIO"
    REVIEW_SCENARIO = "REVIEW_SCENARIO"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class ArtifactType(StrEnum):
    COLLECTED_STORIES = "collected_stories"
    TOPIC_SELECTION = "topic_selection"
    SCENARIO = "scenario"
    CRITIC_REVIEW = "critic_review"
    PROMPT_RESPONSE = "prompt_response"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"


class IdempotencyOutcome(StrEnum):
    INSERTED = "INSERTED"
    DUPLICATE = "DUPLICATE"


class InvocationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True, slots=True)
class PayloadReference:
    """Pointer to durable task payload; not duplicated in queue messages."""

    ref_id: str
    ref_kind: str


@dataclass(frozen=True, slots=True)
class WorkflowRecord:
    workflow_id: str
    state: WorkflowState
    state_version: int
    created_at: datetime
    updated_at: datetime
    revision_count: int = 0
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowTransitionRecord:
    transition_id: str
    workflow_id: str
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str
    occurred_at: datetime
    actor: str | None = None


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    workflow_id: str
    task_type: TaskType
    attempt: int
    status: TaskStatus
    payload_reference: PayloadReference
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    workflow_id: str
    artifact_type: ArtifactType
    name: str
    version: int
    logical_version: int
    is_active: bool
    created_at: datetime
    content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactCreateSpec:
    workflow_id: str
    artifact_type: ArtifactType
    name: str
    version: int
    logical_version: int
    content: JsonValue
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    idempotency_key: str
    workflow_id: str
    task_id: str
    completed_at: datetime
    result_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyInsertSpec:
    idempotency_key: str
    workflow_id: str
    task_id: str
    result_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyInsertResult:
    outcome: IdempotencyOutcome
    record: IdempotencyRecord | None = None


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    outbox_id: str
    workflow_id: str
    task_id: str
    task_type: TaskType
    payload_reference: PayloadReference
    idempotency_key: str
    status: OutboxStatus
    created_at: datetime
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OutboxInsertSpec:
    workflow_id: str
    task_id: str
    task_type: TaskType
    payload_reference: PayloadReference
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TaskLease:
    lease_id: str
    task_id: str
    worker_id: str
    acquired_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AiInvocationRecord:
    invocation_id: str
    workflow_id: str
    task_id: str
    agent_name: str
    agent_version: str
    prompt_version: str
    provider: str
    model: str
    input_artifact_id: str | None
    output_artifact_id: str | None
    attempt: int
    started_at: datetime
    completed_at: datetime | None
    status: InvocationStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AiInvocationInsertSpec:
    workflow_id: str
    task_id: str
    agent_name: str
    agent_version: str
    prompt_version: str
    provider: str
    model: str
    input_artifact_id: str | None
    output_artifact_id: str | None
    attempt: int
    started_at: datetime
    completed_at: datetime | None
    status: InvocationStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None
