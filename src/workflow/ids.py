"""Workflow identifier allocation (LLD §9)."""

from __future__ import annotations

from uuid import uuid4

from persistence.protocols import WorkflowRepo

from .errors import WorkflowConflictError
from .types import InitiateWorkflowRequest


class WorkflowIdAllocator:
    """Allocates and validates workflow identifiers (CG-WF-001)."""

    def allocate(self, request: InitiateWorkflowRequest | None) -> str:
        if request is None or request.workflow_id is None:
            return str(uuid4())
        workflow_id = request.workflow_id.strip()
        if not workflow_id:
            raise ValueError("workflow_id must be non-empty when provided")
        return workflow_id

    def validate_no_duplicate(
        self, workflow_id: str, *, workflow_repo: WorkflowRepo
    ) -> None:
        if workflow_repo.get_workflow(workflow_id) is not None:
            raise WorkflowConflictError(
                f"Workflow {workflow_id} already exists",
                workflow_id=workflow_id,
            )
