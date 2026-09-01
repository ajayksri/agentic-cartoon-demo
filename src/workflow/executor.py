"""Optimistic persistence writes for workflow transitions (LLD §5)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Atomic state + outbox writes — workflow transition
# and outbox row insert share one DB transaction so enqueue intent never diverges.

from __future__ import annotations

from persistence.errors import PersistenceConflictError, PersistenceNotFoundError
from persistence.protocols import ArtifactRepo, OutboxRepo, WorkflowRepo
from persistence.types import WorkflowRecord, WorkflowState as PersistenceWorkflowState
from persistence.types import WorkflowTransitionRecord

from .errors import WorkflowConflictError, WorkflowNotFoundError
from .outbox_builder import OutboxBuildResult, OutboxSpecBuilder
from .records import to_domain_transition
from .transition_table import ApprovalDecision, TransitionDecision
from .types import (
    ApprovalActionResult,
    InitiateWorkflowResult,
    TransitionResult,
    WorkflowState,
)


class TransitionExecutor:
    """Executes persistence sequence for workflow mutations."""

    def __init__(
        self,
        *,
        workflow_repo: WorkflowRepo,
        outbox_repo: OutboxRepo,
        transaction_guard: object,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._outbox_repo = outbox_repo
        self._transaction_guard = transaction_guard

    @staticmethod
    def _to_persistence_state(state: WorkflowState) -> PersistenceWorkflowState:
        return PersistenceWorkflowState(state.value)

    def execute_transition(
        self,
        *,
        workflow: WorkflowRecord,
        decision: TransitionDecision,
        transition: WorkflowTransitionRecord,
        outbox: OutboxBuildResult | None,
        revision_count: int | None = None,
    ) -> tuple[WorkflowRecord, TransitionResult]:
        update_kwargs: dict[str, object] = {
            "expected_version": workflow.state_version,
            "new_state": self._to_persistence_state(decision.to_state),
            "failure_reason": decision.set_failure_reason,
        }
        if revision_count is not None:
            update_kwargs["revision_count"] = revision_count
        try:
            updated = self._workflow_repo.update_workflow_state(
                workflow.workflow_id,
                **update_kwargs,  # type: ignore[arg-type]
            )
        except PersistenceConflictError as exc:
            raise WorkflowConflictError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc
        except PersistenceNotFoundError as exc:
            raise WorkflowNotFoundError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc

        persisted_transition = self._workflow_repo.append_transition(transition)
        outbox_written = False
        enqueued_task = None
        if outbox is not None:
            self._workflow_repo.create_task(
                outbox.task_record, payload=outbox.payload_json
            )
            self._outbox_repo.insert(outbox.outbox_insert)
            outbox_written = True
            enqueued_task = outbox.task_spec

        domain_transition = to_domain_transition(persisted_transition)
        result = TransitionResult(
            workflow_id=workflow.workflow_id,
            from_state=decision.from_state,
            to_state=decision.to_state,
            state_version=updated.state_version,
            transition_id=persisted_transition.transition_id,
            transition=domain_transition,
            outbox_written=outbox_written,
            enqueued_task=enqueued_task,
        )
        return updated, result

    def execute_approval(
        self,
        *,
        workflow: WorkflowRecord,
        decision: ApprovalDecision,
        transition: WorkflowTransitionRecord,
        outbox: OutboxBuildResult | None,
    ) -> tuple[WorkflowRecord, ApprovalActionResult]:
        try:
            updated = self._workflow_repo.update_workflow_state(
                workflow.workflow_id,
                expected_version=workflow.state_version,
                new_state=self._to_persistence_state(decision.to_state),
            )
        except PersistenceConflictError as exc:
            raise WorkflowConflictError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc
        except PersistenceNotFoundError as exc:
            raise WorkflowNotFoundError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc

        persisted_transition = self._workflow_repo.append_transition(transition)
        enqueued_task = None
        if outbox is not None:
            self._workflow_repo.create_task(
                outbox.task_record, payload=outbox.payload_json
            )
            self._outbox_repo.insert(outbox.outbox_insert)
            enqueued_task = outbox.task_spec

        domain_transition = to_domain_transition(persisted_transition)
        result = ApprovalActionResult(
            workflow_id=workflow.workflow_id,
            action=decision.action,
            from_state=decision.from_state,
            to_state=decision.to_state,
            state_version=updated.state_version,
            transition_id=persisted_transition.transition_id,
            transition=domain_transition,
            enqueued_task=enqueued_task,
        )
        return updated, result

    def execute_initiate(
        self,
        *,
        workflow: WorkflowRecord,
        collecting_transition: WorkflowTransitionRecord,
        outbox: OutboxBuildResult,
    ) -> InitiateWorkflowResult:
        try:
            updated = self._workflow_repo.update_workflow_state(
                workflow.workflow_id,
                expected_version=workflow.state_version,
                new_state=PersistenceWorkflowState.COLLECTING,
            )
        except PersistenceConflictError as exc:
            raise WorkflowConflictError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc
        except PersistenceNotFoundError as exc:
            raise WorkflowNotFoundError(
                str(exc), workflow_id=workflow.workflow_id
            ) from exc

        persisted_transition = self._workflow_repo.append_transition(
            collecting_transition
        )
        self._workflow_repo.create_task(outbox.task_record, payload=outbox.payload_json)
        self._outbox_repo.insert(outbox.outbox_insert)

        domain_transition = to_domain_transition(persisted_transition)
        return InitiateWorkflowResult(
            workflow_id=workflow.workflow_id,
            state=WorkflowState.COLLECTING,
            state_version=updated.state_version,
            transition=domain_transition,
            enqueued_task=outbox.task_spec,
        )

    def recreate_expected_outbox(
        self,
        *,
        workflow: WorkflowRecord,
        expected_task_type: object,
        artifact_repo: ArtifactRepo,
        outbox_builder: OutboxSpecBuilder,
        attempt: int = 1,
    ) -> OutboxBuildResult:
        from config.types import TaskType

        task_type = (
            expected_task_type
            if isinstance(expected_task_type, TaskType)
            else TaskType(str(expected_task_type))
        )
        logical_version = outbox_builder._logical_version_tracker.resolve_for_task(
            workflow_id=workflow.workflow_id,
            task_type=task_type,
            artifact_repo=artifact_repo,
            increment=task_type == TaskType.GENERATE_SCENARIO,
        )
        outbox = outbox_builder.build(
            workflow=workflow,
            task_type=task_type,
            logical_version=logical_version,
            attempt=attempt,
        )
        self._workflow_repo.create_task(outbox.task_record, payload=outbox.payload_json)
        self._outbox_repo.insert(outbox.outbox_insert)
        return outbox
