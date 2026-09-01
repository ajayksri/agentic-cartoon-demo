"""Persistence → config/workflow mappers (LLD §2.7)."""

from __future__ import annotations

from config.types import TaskType as ConfigTaskType
from persistence.types import TaskRecord, TaskStatus as PersistenceTaskStatus
from workflow.types import WorkflowState


def to_config_task_type(record: TaskRecord) -> ConfigTaskType:
    """Map persistence.TaskType token → config.TaskType via .value equality."""
    return ConfigTaskType(record.task_type.value)


def to_workflow_state(token: str) -> WorkflowState:
    """Map persistence workflow state token → workflow.WorkflowState."""
    return WorkflowState(token)


def to_persistence_task_status(status: PersistenceTaskStatus) -> PersistenceTaskStatus:
    """Worker-internal writes only — identity mapper for persistence TaskStatus."""
    return status
