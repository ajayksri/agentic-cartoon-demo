"""Workflow engine module public surface."""

from __future__ import annotations

from .errors import (
    InvalidApprovalActionError,
    InvalidTransitionError,
    WorkflowConflictError,
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowTerminalError,
)
from .protocols import WorkflowEngine, create_workflow_engine
from .types import (
    TERMINAL_WORKFLOW_STATES,
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    OutboxTaskSpec,
    ReconciliationReport,
    ReconciliationResult,
    TimelineEvent,
    TransitionRecord,
    TransitionRequest,
    TransitionResult,
    TransitionSignal,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowState,
    WorkflowStatus,
    WorkflowTimeline,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "TERMINAL_WORKFLOW_STATES",
    "ApprovalAction",
    "ApprovalActionResult",
    "InitiateWorkflowRequest",
    "InitiateWorkflowResult",
    "InvalidApprovalActionError",
    "InvalidTransitionError",
    "OutboxTaskSpec",
    "ReconciliationReport",
    "ReconciliationResult",
    "TimelineEvent",
    "TransitionRecord",
    "TransitionRequest",
    "TransitionResult",
    "TransitionSignal",
    "WorkflowConflictError",
    "WorkflowEngine",
    "WorkflowError",
    "WorkflowHistory",
    "WorkflowNotFoundError",
    "WorkflowOutput",
    "WorkflowState",
    "WorkflowStatus",
    "WorkflowTerminalError",
    "WorkflowTimeline",
    "create_workflow_engine",
]
