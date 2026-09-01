"""Persistence → domain record mappers (LLD §2.6)."""

from __future__ import annotations

from persistence.types import WorkflowTransitionRecord

from .types import TaskType, TransitionRecord, WorkflowState


def to_domain_workflow_state(token: str) -> WorkflowState:
    """Validate token against workflow.WorkflowState."""
    return WorkflowState(token)


def to_domain_task_type(token: str) -> TaskType:
    return TaskType(token)


def to_domain_transition(record: WorkflowTransitionRecord) -> TransitionRecord:
    """Map persistence append row → public TransitionRecord."""
    return TransitionRecord(
        transition_id=record.transition_id,
        workflow_id=record.workflow_id,
        from_state=to_domain_workflow_state(record.from_state.value),
        to_state=to_domain_workflow_state(record.to_state.value),
        reason=record.reason,
        occurred_at=record.occurred_at,
        actor=record.actor,
    )
