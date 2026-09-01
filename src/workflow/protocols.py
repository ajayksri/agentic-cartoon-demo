"""Public workflow engine protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from config.types import AppConfig

from .types import (
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    ReconciliationResult,
    TransitionRequest,
    TransitionResult,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowStatus,
    WorkflowTimeline,
)

if TYPE_CHECKING:
    from persistence.protocols import (
        ArtifactRepo,
        OutboxRepo,
        TransactionManager,
        WorkflowRepo,
    )


class WorkflowEngine(Protocol):
    """State machine authority: transitions, task/outbox creation, read models."""

    def initiate_workflow(
        self,
        *,
        config: AppConfig,
        request: InitiateWorkflowRequest | None = None,
    ) -> InitiateWorkflowResult:
        """Create workflow, transition to COLLECTING, enqueue COLLECT outbox task."""
        ...

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        """Validate and apply a stage transition; write outbox when required."""
        ...

    def apply_approval_action(
        self,
        *,
        workflow_id: str,
        action: ApprovalAction,
        actor: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalActionResult:
        """Apply human approval action from AWAITING_HUMAN_APPROVAL."""
        ...

    def reconcile_stuck_workflows(
        self,
        *,
        config: AppConfig,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        """Scan and repair incomplete transitions (coordinator loop)."""
        ...

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        """Return current workflow snapshot."""
        ...

    def get_workflow_history(self, workflow_id: str) -> WorkflowHistory:
        """Return ordered transition history."""
        ...

    def get_workflow_output(self, workflow_id: str) -> WorkflowOutput:
        """Return aggregated output package."""
        ...

    def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimeline:
        """Return human-readable ordered timeline."""
        ...


def create_workflow_engine(
    *,
    config: AppConfig,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    outbox_repo: OutboxRepo,
    transaction_manager: TransactionManager,
) -> WorkflowEngine:
    """Create the default WorkflowEngine implementation for the composition root."""
    from .engine import create_workflow_engine as _create

    return _create(
        config=config,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        outbox_repo=outbox_repo,
        transaction_manager=transaction_manager,
    )
