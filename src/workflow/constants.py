"""Workflow engine internal constants (LLD §2.5, §12)."""

# GUARDRAIL: Workflow — terminal and pause states define where autonomous execution must stop.

from __future__ import annotations

from config.types import TaskType

from .types import WorkflowState

TERMINAL_STATES: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.NO_SUITABLE_TOPIC,
        WorkflowState.APPROVED,
        WorkflowState.REJECTED,
        WorkflowState.REVIEW_FAILED,
        WorkflowState.FAILED,
        WorkflowState.FAILED_PERMANENTLY,
    }
)

PAUSE_STATES: frozenset[WorkflowState] = frozenset({WorkflowState.AWAITING_HUMAN_APPROVAL})

TRANSIENT_STATES: frozenset[WorkflowState] = frozenset(
    state for state in WorkflowState if state not in TERMINAL_STATES and state not in PAUSE_STATES
)

IDEMPOTENCY_KEY_FORMAT = "{workflow_id}:{task_type}:{logical_version}"
TASK_PAYLOAD_REF_KIND = "task_payload"

STUCK_THRESHOLD_SHORT_STATES: frozenset[WorkflowState] = frozenset(
    {
        WorkflowState.COLLECTING,
        WorkflowState.SELECTING_TOPIC,
        WorkflowState.GENERATING_SCENARIO,
        WorkflowState.REVIEWING,
    }
)

DEFAULT_STUCK_THRESHOLD_SHORT_SECONDS: float = 30 * 60
DEFAULT_STUCK_THRESHOLD_LONG_SECONDS: float = 60 * 60

_IN_FLIGHT_TASK_STATUSES = frozenset({"PENDING", "DISPATCHED", "IN_PROGRESS"})


def stuck_threshold_seconds(state: WorkflowState) -> float:
    """Return stuck-state timeout threshold for *state* (LLD §12)."""
    if state in STUCK_THRESHOLD_SHORT_STATES:
        return DEFAULT_STUCK_THRESHOLD_SHORT_SECONDS
    if state in TRANSIENT_STATES:
        return DEFAULT_STUCK_THRESHOLD_LONG_SECONDS
    return float("inf")


def format_idempotency_key_template() -> str:
    """Documented idempotency key format (CG-WF-002)."""
    return IDEMPOTENCY_KEY_FORMAT


__all__ = [
    "DEFAULT_STUCK_THRESHOLD_LONG_SECONDS",
    "DEFAULT_STUCK_THRESHOLD_SHORT_SECONDS",
    "IDEMPOTENCY_KEY_FORMAT",
    "PAUSE_STATES",
    "STUCK_THRESHOLD_SHORT_STATES",
    "TASK_PAYLOAD_REF_KIND",
    "TERMINAL_STATES",
    "TRANSIENT_STATES",
    "stuck_threshold_seconds",
]
