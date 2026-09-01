"""Default workflow engine orchestration (LLD §16)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Durable state as source of truth — workflow state
# lives in PostgreSQL, not LLM memory; agents read/write only through this engine.
# GUARDRAIL: Workflow — agents never apply transitions; only this engine mutates workflow state.

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from config.types import AppConfig, TaskType
from persistence.protocols import (
    ArtifactRepo,
    OutboxRepo,
    TransactionManager,
    WorkflowRepo,
)
from persistence.types import WorkflowState as PersistenceWorkflowState
from persistence.types import WorkflowTransitionRecord

from .errors import (
    InvalidApprovalActionError,
    InvalidTransitionError,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowTerminalError,
)
from .executor import TransitionExecutor
from .ids import WorkflowIdAllocator
from .outbox_builder import LogicalVersionTracker, OutboxSpecBuilder
from .read_models import ReadModelAssembler
from .reconcile import ReconciliationScanner
from .records import to_domain_workflow_state
from .telemetry import WorkflowTelemetry
from .transition_table import TransitionTable
from .types import (
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    ReconciliationResult,
    TransitionRequest,
    TransitionResult,
    TransitionSignal,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowState,
    WorkflowStatus,
    WorkflowTimeline,
    TERMINAL_WORKFLOW_STATES,
)


class TransactionGuard:
    """Enforces active transaction before mutating operations (CG-WF-HLD-003)."""

    def __init__(self, transaction_manager: TransactionManager) -> None:
        self._txn_manager = transaction_manager

    def require_active(self, *, operation: str) -> None:
        checker = getattr(self._txn_manager, "is_in_transaction", None)
        if not callable(checker) or not checker():
            raise RuntimeError(
                f"{operation} requires an active transaction; "
                "use `with transaction_manager.transaction():` before calling"
            )


class DefaultWorkflowEngine:
    """State machine authority with injected persistence repositories."""

    def __init__(
        self,
        *,
        config: AppConfig,
        workflow_repo: WorkflowRepo,
        artifact_repo: ArtifactRepo,
        outbox_repo: OutboxRepo,
        transaction_manager: TransactionManager,
        transition_table: TransitionTable,
        outbox_builder: OutboxSpecBuilder,
        executor: TransitionExecutor,
        read_model_assembler: ReadModelAssembler,
        telemetry: WorkflowTelemetry,
        workflow_id_allocator: WorkflowIdAllocator,
        transaction_guard: TransactionGuard,
        reconciliation_scanner: ReconciliationScanner | None = None,
    ) -> None:
        self._config = config
        self._workflow_repo = workflow_repo
        self._artifact_repo = artifact_repo
        self._outbox_repo = outbox_repo
        self._transaction_manager = transaction_manager
        self._transition_table = transition_table
        self._outbox_builder = outbox_builder
        self._executor = executor
        self._read_model_assembler = read_model_assembler
        self._telemetry = telemetry
        self._workflow_id_allocator = workflow_id_allocator
        self._transaction_guard = transaction_guard
        self._reconciliation_scanner = reconciliation_scanner

    def _build_transition(
        self,
        *,
        workflow_id: str,
        from_state: WorkflowState,
        to_state: WorkflowState,
        reason: str,
        actor: str | None = None,
    ) -> WorkflowTransitionRecord:
        now = datetime.now(UTC)
        return WorkflowTransitionRecord(
            transition_id=str(uuid4()),
            workflow_id=workflow_id,
            from_state=PersistenceWorkflowState(from_state.value),
            to_state=PersistenceWorkflowState(to_state.value),
            reason=reason,
            occurred_at=now,
            actor=actor,
        )

    def initiate_workflow(
        self,
        *,
        config: AppConfig,
        request: InitiateWorkflowRequest | None = None,
    ) -> InitiateWorkflowResult:
        self._transaction_guard.require_active(operation="initiate_workflow")
        workflow_id = self._workflow_id_allocator.allocate(request)
        self._workflow_id_allocator.validate_no_duplicate(
            workflow_id, workflow_repo=self._workflow_repo
        )
        span = self._telemetry.emit_initiated(workflow_id=workflow_id)
        try:
            workflow = self._workflow_repo.create_workflow(
                workflow_id, initial_state=PersistenceWorkflowState.CREATED
            )
            outbox = self._outbox_builder.build(
                workflow=workflow,
                task_type=TaskType.COLLECT,
                logical_version=1,
            )
            transition = self._build_transition(
                workflow_id=workflow_id,
                from_state=WorkflowState.CREATED,
                to_state=WorkflowState.COLLECTING,
                reason="workflow_initiated",
                actor=request.actor if request else None,
            )
            result = self._executor.execute_initiate(
                workflow=workflow,
                collecting_transition=transition,
                outbox=outbox,
            )
            self._telemetry.emit_transition(
                workflow_id=workflow_id,
                from_state=WorkflowState.CREATED.value,
                to_state=WorkflowState.COLLECTING.value,
                signal="initiate",
                task_type=TaskType.COLLECT.value,
            )
            self._telemetry.record_transition_metric(
                signal="initiate", task_type=TaskType.COLLECT.value
            )
            return result
        finally:
            span.end()

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        self._transaction_guard.require_active(operation="apply_transition")
        workflow = self._workflow_repo.get_workflow(request.workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(
                f"Workflow {request.workflow_id} not found",
                workflow_id=request.workflow_id,
            )
        current_state = to_domain_workflow_state(workflow.state.value)
        if current_state != request.expected_state:
            raise WorkflowConflictError(
                f"Expected state {request.expected_state.value} but found {current_state.value}",
                workflow_id=request.workflow_id,
            )
        if current_state in TERMINAL_WORKFLOW_STATES:
            exc = InvalidTransitionError(
                f"Cannot transition from terminal state {current_state.value}",
                workflow_id=request.workflow_id,
                from_state=current_state,
                signal=request.signal,
            )
            self._telemetry.emit_invalid_transition(
                workflow_id=request.workflow_id,
                error_class=exc.code,
                from_state=current_state.value,
                signal=request.signal.value,
            )
            self._telemetry.record_transition_error_metric(error_class=exc.code)
            raise exc

        try:
            decision = self._transition_table.lookup(
                current_state=current_state,
                signal=request.signal,
                revision_count=workflow.revision_count,
                max_scenario_revisions=self._config.workflow.max_scenario_revisions,
            )
        except InvalidTransitionError as exc:
            self._telemetry.emit_invalid_transition(
                workflow_id=request.workflow_id,
                error_class=exc.code,
                from_state=current_state.value,
                signal=request.signal.value,
            )
            self._telemetry.record_transition_error_metric(error_class=exc.code)
            raise InvalidTransitionError(
                str(exc),
                workflow_id=request.workflow_id,
                from_state=current_state,
                signal=request.signal,
            ) from exc

        failure_reason = decision.set_failure_reason
        if failure_reason is None and request.signal in {
            TransitionSignal.UNRECOVERABLE_ERROR,
            TransitionSignal.RETRIES_EXHAUSTED,
        }:
            failure_reason = request.reason
        if failure_reason is not None and decision.set_failure_reason is None:
            decision = replace(decision, set_failure_reason=failure_reason)

        outbox = self._outbox_builder.build_for_decision(
            workflow=workflow,
            decision=decision,
            artifact_repo=self._artifact_repo,
        )
        transition = self._build_transition(
            workflow_id=request.workflow_id,
            from_state=current_state,
            to_state=decision.to_state,
            reason=request.reason,
            actor=request.actor,
        )
        new_revision = (
            workflow.revision_count + 1
            if decision.increment_revision_count
            else None
        )
        _, result = self._executor.execute_transition(
            workflow=workflow,
            decision=decision,
            transition=transition,
            outbox=outbox,
            revision_count=new_revision,
        )
        task_type = (
            result.enqueued_task.task_type.value if result.enqueued_task else None
        )
        self._telemetry.emit_transition(
            workflow_id=request.workflow_id,
            from_state=current_state.value,
            to_state=decision.to_state.value,
            signal=request.signal.value,
            task_type=task_type,
        )
        self._telemetry.record_transition_metric(
            signal=request.signal.value, task_type=task_type
        )
        return result

    def apply_approval_action(
        self,
        *,
        workflow_id: str,
        action: ApprovalAction,
        actor: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalActionResult:
        self._transaction_guard.require_active(operation="apply_approval_action")
        workflow = self._workflow_repo.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id} not found", workflow_id=workflow_id
            )
        current_state = to_domain_workflow_state(workflow.state.value)
        if current_state != WorkflowState.AWAITING_HUMAN_APPROVAL:
            if current_state in TERMINAL_WORKFLOW_STATES:
                raise WorkflowTerminalError(
                    f"Workflow {workflow_id} is terminal in state {current_state.value}",
                    workflow_id=workflow_id,
                    state=current_state,
                )
            raise InvalidApprovalActionError(
                f"Approval action {action.value} invalid in state {current_state.value}",
                workflow_id=workflow_id,
                action=action,
                current_state=current_state,
            )

        decision = self._transition_table.lookup_approval(action=action)
        outbox = self._outbox_builder.build_for_decision(
            workflow=workflow,
            decision=decision,
            artifact_repo=self._artifact_repo,
        )
        transition = self._build_transition(
            workflow_id=workflow_id,
            from_state=current_state,
            to_state=decision.to_state,
            reason=f"approval_{action.value}",
            actor=actor,
        )
        _, result = self._executor.execute_approval(
            workflow=workflow,
            decision=decision,
            transition=transition,
            outbox=outbox,
        )
        self._telemetry.emit_approval(
            workflow_id=workflow_id,
            action=action.value,
            from_state=current_state.value,
            to_state=decision.to_state.value,
        )
        return result

    def reconcile_stuck_workflows(
        self,
        *,
        config: AppConfig,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        if self._reconciliation_scanner is None:
            raise RuntimeError("Reconciliation scanner not configured")
        return self._reconciliation_scanner.scan_and_repair(batch_size=batch_size)

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        record = self._workflow_repo.get_workflow(workflow_id)
        if record is None:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id} not found", workflow_id=workflow_id
            )
        return self._read_model_assembler.assemble_status(record)

    def get_workflow_history(self, workflow_id: str) -> WorkflowHistory:
        if self._workflow_repo.get_workflow(workflow_id) is None:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id} not found", workflow_id=workflow_id
            )
        return self._read_model_assembler.assemble_history(workflow_id)

    def get_workflow_output(self, workflow_id: str) -> WorkflowOutput:
        workflow = self._workflow_repo.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id} not found", workflow_id=workflow_id
            )
        return self._read_model_assembler.assemble_output(workflow=workflow)

    def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimeline:
        if self._workflow_repo.get_workflow(workflow_id) is None:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id} not found", workflow_id=workflow_id
            )
        return self._read_model_assembler.assemble_timeline(workflow_id=workflow_id)


def create_workflow_engine(
    *,
    config: AppConfig,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    outbox_repo: OutboxRepo,
    transaction_manager: TransactionManager,
    telemetry: WorkflowTelemetry | None = None,
) -> DefaultWorkflowEngine:
    """Wire DefaultWorkflowEngine with injected repos and WorkflowTelemetry."""
    transition_table = TransitionTable()
    logical_version_tracker = LogicalVersionTracker()
    outbox_builder = OutboxSpecBuilder(logical_version_tracker=logical_version_tracker)
    transaction_guard = TransactionGuard(transaction_manager=transaction_manager)
    executor = TransitionExecutor(
        workflow_repo=workflow_repo,
        outbox_repo=outbox_repo,
        transaction_guard=transaction_guard,
    )
    read_model_assembler = ReadModelAssembler(
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
    )
    telemetry_impl = telemetry or WorkflowTelemetry()
    allocator = WorkflowIdAllocator()
    engine = DefaultWorkflowEngine(
        config=config,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        outbox_repo=outbox_repo,
        transaction_manager=transaction_manager,
        transition_table=transition_table,
        outbox_builder=outbox_builder,
        executor=executor,
        read_model_assembler=read_model_assembler,
        telemetry=telemetry_impl,
        workflow_id_allocator=allocator,
        transaction_guard=transaction_guard,
    )
    reconciliation_scanner = ReconciliationScanner(
        config=config,
        workflow_repo=workflow_repo,
        outbox_repo=outbox_repo,
        artifact_repo=artifact_repo,
        executor=executor,
        outbox_builder=outbox_builder,
        transition_table=transition_table,
        engine=engine,
        transaction_guard=transaction_guard,
        transaction_manager=transaction_manager,
    )
    engine._reconciliation_scanner = reconciliation_scanner
    return engine
