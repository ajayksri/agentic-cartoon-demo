"""Default worker consume loop (LLD §8)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Worker execution pipeline — dequeue → idempotency check
# → lease acquire → agent invoke → workflow transition → persist → ACK. This is the
# production glue that makes non-deterministic AI safe under at-least-once delivery.

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from config.types import AppConfig, InjectionId, TaskType
from observability import get_correlation_context
from persistence.types import IdempotencyInsertSpec, TaskStatus as PersistenceTaskStatus
from task_queue.types import PendingDelivery, TaskMessage
from workflow.errors import WorkflowConflictError
from workflow.types import (
    TransitionRequest,
    TransitionResult,
    TransitionSignal,
    WorkflowState,
)

from .concurrency import ConcurrencyPool
from .context import TaskExecutionContextBuilder
from .constants import DEFAULT_SHUTDOWN_GRACE_SECONDS
from .errors import (
    HandlerNotFoundError,
    LeaseConflictError,
    RetryExhaustedError,
    TaskExecutionError,
    TaskRecordNotFoundError,
    WorkerShutdownError,
)
from .idempotency import DefaultIdempotencyOrchestrator, resolve_logical_version
from .lease import LeaseCoordinator
from .messages import (
    execution_error_message,
    retry_exhausted_message,
    shutdown_message,
    task_not_found_message,
)
from .records import to_config_task_type, to_workflow_state
from .registry import DefaultTaskHandlerRegistry
from .retry import RetryClassifier
from .state_mapping import WorkflowStateGuard
from .telemetry import RecordingWorkerTelemetry, WorkerTelemetry
from .types import (
    DuplicateResolution,
    IdempotencyPhase,
    TaskExecutionContext,
    TaskHandlerOutcome,
    TaskHandlerResult,
    TaskTiming,
    WorkerLoopConfig,
)

if TYPE_CHECKING:
    from observability.protocols import Logger, Meter, Span, Tracer
    from persistence.protocols import (
        ArtifactRepo,
        IdempotencyRepo,
        TaskLeaseRepo,
        TransactionManager,
        WorkflowRepo,
    )
    from persistence.types import TaskRecord, WorkflowRecord
    from task_queue.protocols import TaskQueue
    from workflow.protocols import WorkflowEngine


class _SimulatedCrashBeforeAck(Exception):
    """Test seam: crash after handler before durable commit."""


@dataclass
class DeliveryContext:
    """Mutable orchestration frame for one PendingDelivery."""

    delivery: PendingDelivery
    task_record: TaskRecord
    workflow_record: WorkflowRecord
    task_type: TaskType
    workflow_state: WorkflowState
    idempotency_key: str = ""
    timing: TaskTiming | None = None
    lease_id: str | None = None
    effective_attempt: int = 1
    duplicate_resolution: DuplicateResolution | None = None
    handler_result: TaskHandlerResult | None = None


class TransactionGuard:
    """Ensures handler operations run inside an active transaction."""

    def __init__(self, transaction_manager: TransactionManager) -> None:
        self._transaction_manager = transaction_manager

    def require_active(self, *, operation: str) -> None:
        if not self._transaction_manager.is_in_transaction():
            raise RuntimeError(
                f"{operation} requires an active transaction; use transaction_manager.transaction()"
            )


class DefaultWorkerLoop:
    """Long-running task consume/process loop."""

    def __init__(
        self,
        *,
        config: AppConfig,
        loop_config: WorkerLoopConfig,
        registry: DefaultTaskHandlerRegistry,
        task_queue: TaskQueue,
        task_lease_repo: TaskLeaseRepo,
        workflow_engine: WorkflowEngine,
        workflow_repo: WorkflowRepo,
        artifact_repo: ArtifactRepo,
        idempotency_orchestrator: DefaultIdempotencyOrchestrator,
        transaction_manager: TransactionManager,
        failure_injection: object,
        collector: object,
        topic_selection_agent: object,
        scenario_generation_agent: object,
        critic_agent: object,
        model_provider_factory: Callable,
        logger: Logger,
        meter: Meter,
        tracer: Tracer,
        worker_id: str | None = None,
        clock: Callable[[], datetime] | None = None,
        telemetry: WorkerTelemetry | None = None,
    ) -> None:
        self._config = config
        self._loop_config = loop_config
        self._registry = registry
        self._task_queue = task_queue
        self._task_lease_repo = task_lease_repo
        self._workflow_engine = workflow_engine
        self._workflow_repo = workflow_repo
        self._artifact_repo = artifact_repo
        self._orchestrator = idempotency_orchestrator
        self._transaction_manager = transaction_manager
        self._failure_injection = failure_injection
        self._collector = collector
        self._topic_selection_agent = topic_selection_agent
        self._scenario_generation_agent = scenario_generation_agent
        self._critic_agent = critic_agent
        self._model_provider_factory = model_provider_factory
        self._logger = logger
        self._meter = meter
        self._tracer = tracer
        self._worker_id = worker_id or loop_config.consumer_name
        self._clock = clock or (lambda: datetime.now(UTC))
        self._shutdown_event = threading.Event()
        self._in_flight = 0
        self._in_flight_lock = threading.Lock()
        self._lease_coordinator = LeaseCoordinator(task_lease_repo=task_lease_repo, clock=self._clock)
        self._retry_classifier = RetryClassifier(config=config, clock=self._clock)
        self._concurrency_pool = ConcurrencyPool(config=config, clock=self._clock)
        self._state_guard = WorkflowStateGuard()
        self.telemetry = telemetry or WorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        self._transaction_guard = TransactionGuard(transaction_manager)
        self._recorded_resolutions: list[str] = []
        self._event_order: list[str] = []

    def run(self) -> None:
        self._task_queue.ensure_consumer_group(
            self._loop_config.stream,
            self._loop_config.consumer_group,
        )
        try:
            while not self._shutdown_event.is_set():
                delivery = self._task_queue.dequeue(
                    self._loop_config.stream,
                    consumer_group=self._loop_config.consumer_group,
                    consumer_name=self._loop_config.consumer_name,
                    block_ms=self._loop_config.block_ms,
                )
                if delivery is None:
                    continue
                self._concurrency_pool.submit(self._process_delivery_wrapper, delivery)
        finally:
            self._concurrency_pool.shutdown(
                wait=True,
                timeout=self._loop_config.shutdown_grace_seconds,
            )
            if self._in_flight > 0:
                raise WorkerShutdownError(
                    shutdown_message(detail="Mandatory work incomplete after grace period")
                )

    def stop(self) -> None:
        self._shutdown_event.set()

    def run_once(self) -> None:
        delivery = self._task_queue.dequeue(
            self._loop_config.stream,
            consumer_group=self._loop_config.consumer_group,
            consumer_name=self._loop_config.consumer_name,
            block_ms=0,
        )
        if delivery is not None:
            self._process_delivery(delivery)

    def process_delivery_without_ack(self, delivery: PendingDelivery) -> None:
        self._process_delivery(delivery, skip_ack=True)

    def _process_delivery_wrapper(self, delivery: PendingDelivery) -> None:
        self._process_delivery(delivery)

    def _process_delivery(
        self,
        delivery: PendingDelivery,
        *,
        skip_ack: bool = False,
    ) -> None:
        now = self._clock()
        message = delivery.message
        timing = TaskTiming(enqueued_at=message.created_at, dequeued_at=now)
        task_record = self._workflow_repo.get_task(message.task_id)
        if task_record is None:
            self._logger.error(
                "task_not_found",
                task_not_found_message(task_id=message.task_id),
                task_id=message.task_id,
            )
            return
        workflow_record = self._workflow_repo.get_workflow(message.workflow_id)
        if workflow_record is None:
            self._logger.error(
                "task_not_found",
                task_not_found_message(task_id=message.task_id),
                task_id=message.task_id,
            )
            return
        workflow_state = to_workflow_state(workflow_record.state.value)
        task_type = to_config_task_type(task_record)
        stale = self._state_guard.classify_stale_task(
            workflow_state=workflow_state,
            task_type=task_type,
        )
        if stale.action != "proceed":
            self.telemetry.record_stale_ignored(
                reason=stale.reason or stale.action,
                workflow_id=message.workflow_id,
                task_id=message.task_id,
            )
            if not skip_ack:
                self._task_queue.ack(delivery)
            return
        effective_attempt = self._retry_classifier.effective_attempt(
            task_record=task_record,
            message=message,
        )
        if self._retry_classifier.should_defer(task_id=message.task_id):
            return
        slot = self._concurrency_pool.acquire_blocking(task_type)
        lease_id: str | None = None
        try:
            with self._in_flight_lock:
                self._in_flight += 1
            try:
                lease = self._lease_coordinator.acquire(
                    task_id=message.task_id,
                    worker_id=self._worker_id,
                )
                lease_id = lease.lease_id
                self._lease_coordinator.start_renewal(lease_id=lease_id)
                logical_version = resolve_logical_version(
                    task_type=task_type,
                    task_record=task_record,
                    delivery=delivery,
                    artifact_repo=self._artifact_repo,
                    workflow_repo=self._workflow_repo,
                )
                idempotency_key = self._orchestrator.build_idempotency_key(
                    workflow_id=message.workflow_id,
                    task_type=task_type,
                    logical_version=logical_version,
                )
                pre = self._orchestrator.check_before_execution(idempotency_key=idempotency_key)
                if pre.phase == IdempotencyPhase.ALREADY_COMPLETED:
                    resolution = DuplicateResolution.IGNORED_BEFORE_EXECUTION
                    self._recorded_resolutions.append(resolution.value)
                    self.telemetry.record_duplicate(task_type=task_type, resolution=resolution)
                    self._failure_injection.invoke_if_active(InjectionId.FINJ_WKR_PRE_ACK)
                    if not skip_ack:
                        self._task_queue.ack(delivery)
                    return
                ctx = DeliveryContext(
                    delivery=delivery,
                    task_record=task_record,
                    workflow_record=workflow_record,
                    task_type=task_type,
                    workflow_state=workflow_state,
                    idempotency_key=idempotency_key,
                    timing=timing,
                    effective_attempt=effective_attempt,
                )
                exec_context = self._build_execution_context(
                    delivery=delivery,
                    task_record=task_record,
                    idempotency_key=idempotency_key,
                    timing=timing,
                )
                self._failure_injection.invoke_if_active(InjectionId.FINJ_WKR_PRE)
                handler_started = self._clock()
                timing = TaskTiming(
                    enqueued_at=timing.enqueued_at,
                    dequeued_at=timing.dequeued_at,
                    handler_started_at=handler_started,
                )
                with self._task_correlation_scope(
                    message=message,
                    effective_attempt=effective_attempt,
                ):
                    span = self.telemetry.record_task_started(
                        workflow_id=message.workflow_id,
                        task_id=message.task_id,
                        task_type=task_type,
                        attempt=effective_attempt,
                        trace_carrier=dict(message.trace_carrier),
                    )
                    try:
                        with self._transaction_manager.transaction():
                            self._transaction_guard.require_active(operation="handle_task")
                            handler = self._registry.get_handler(task_type)
                            handler_result = handler.handle(exec_context)
                            handler_finished = self._clock()
                            timing = TaskTiming(
                                enqueued_at=timing.enqueued_at,
                                dequeued_at=timing.dequeued_at,
                                handler_started_at=handler_started,
                                handler_finished_at=handler_finished,
                            )
                            if skip_ack:
                                raise _SimulatedCrashBeforeAck()
                            self._commit_success_path(
                                ctx=ctx,
                                handler_result=handler_result,
                                timing=timing,
                            )
                        self._event_order.append("commit")
                        self._event_order.append("transition")
                        self._failure_injection.invoke_if_active(InjectionId.FINJ_WKR_POST_COMMIT)
                    finally:
                        span.end()
                    self._lease_coordinator.stop_renewal(lease_id=lease_id)
                    self._lease_coordinator.release(lease_id=lease_id)
                    lease_id = None
                    self._failure_injection.invoke_if_active(InjectionId.FINJ_WKR_PRE_ACK)
                    if not skip_ack:
                        self._task_queue.ack(delivery)
                        self._event_order.append("ack")
                    self.telemetry.record_completion(
                        timing=timing,
                        task_type=task_type,
                        duplicate_resolution=ctx.duplicate_resolution,
                    )
            except _SimulatedCrashBeforeAck:
                pass
            except LeaseConflictError as err:
                resolution = DuplicateResolution.DETECTED_DURING_EXECUTION
                self._recorded_resolutions.append(resolution.value)
                self.telemetry.record_lease_conflict(
                    task_id=err.task_id,
                    worker_id=err.worker_id,
                )
                self.telemetry.record_duplicate(task_type=task_type, resolution=resolution)
            except HandlerNotFoundError as err:
                self._handle_permanent_failure(
                    delivery=delivery,
                    task_type=err.task_type,
                    task_record=task_record,
                    effective_attempt=effective_attempt,
                    error_class=err.code,
                    exhausted=False,
                    skip_ack=skip_ack,
                )
            except Exception as err:
                retryable, error_class = self._retry_classifier.classify_exception(err)
                if retryable and not self._retry_classifier.is_exhausted(
                    attempt=effective_attempt,
                    task_type=task_type,
                ):
                    self._handle_retryable_failure(
                        task_record=task_record,
                        task_type=task_type,
                        effective_attempt=effective_attempt,
                        error_class=error_class,
                        reason=str(err),
                    )
                else:
                    self._handle_permanent_failure(
                        delivery=delivery,
                        task_type=task_type,
                        task_record=task_record,
                        effective_attempt=effective_attempt,
                        error_class=error_class,
                        exhausted=self._retry_classifier.is_exhausted(
                            attempt=effective_attempt,
                            task_type=task_type,
                        ),
                        skip_ack=skip_ack,
                    )
        finally:
            if lease_id is not None:
                self._lease_coordinator.stop_renewal(lease_id=lease_id)
                self._lease_coordinator.release(lease_id=lease_id)
            self._concurrency_pool.release(slot)
            with self._in_flight_lock:
                self._in_flight -= 1

    def _build_execution_context(
        self,
        *,
        delivery: PendingDelivery,
        task_record: TaskRecord,
        idempotency_key: str,
        timing: TaskTiming,
    ) -> TaskExecutionContext:
        return TaskExecutionContextBuilder.build(
            worker_id=self._worker_id,
            config=self._config,
            delivery=delivery,
            task_record=task_record,
            idempotency_key=idempotency_key,
            timing=timing,
            workflow_engine=self._workflow_engine,
            workflow_repo=self._workflow_repo,
            artifact_repo=self._artifact_repo,
            idempotency_orchestrator=self._orchestrator,
            transaction_manager=self._transaction_manager,
            failure_injection=self._failure_injection,
            logger=self._logger,
            meter=self._meter,
            tracer=self._tracer,
            collector=self._collector,
            topic_selection_agent=self._topic_selection_agent,
            scenario_generation_agent=self._scenario_generation_agent,
            critic_agent=self._critic_agent,
            model_provider_factory=self._model_provider_factory,
        )

    @staticmethod
    def _task_correlation_scope(
        *,
        message: TaskMessage,
        effective_attempt: int,
    ) -> AbstractContextManager[None]:
        correlation = get_correlation_context()
        stack = ExitStack()
        if message.trace_carrier:
            trace_ctx = correlation.extract(dict(message.trace_carrier))
            stack.enter_context(correlation.attach(trace_ctx))
        stack.enter_context(
            correlation.bind(
                workflow_id=message.workflow_id,
                task_id=message.task_id,
                task_attempt=effective_attempt,
            )
        )
        return stack

    def _commit_success_path(
        self,
        *,
        ctx: DeliveryContext | object,
        handler_result: TaskHandlerResult,
        timing: TaskTiming | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        if handler_result.outcome not in {
            TaskHandlerOutcome.COMPLETED,
            TaskHandlerOutcome.DUPLICATE_REUSED,
        }:
            task_type = getattr(ctx, "task_type", TaskType.COLLECT)
            workflow_id = getattr(ctx, "workflow_id", "")
            task_id = getattr(ctx, "task_id", "")
            retryable, _ = self._retry_classifier.classify_handler_result(handler_result)
            raise TaskExecutionError(
                execution_error_message(
                    workflow_id=workflow_id,
                    task_id=task_id,
                    task_type=task_type,
                    detail=handler_result.reason or "handler failure",
                ),
                workflow_id=workflow_id,
                task_id=task_id,
                task_type=task_type,
                retryable=retryable,
            )
        delivery = getattr(ctx, "delivery", None)
        if delivery is not None:
            message = delivery.message
            task_type = ctx.task_type
            key = idempotency_key or ctx.idempotency_key
        else:
            message = None
            task_type = getattr(ctx, "task_type", TaskType.COLLECT)
            key = idempotency_key or ""
        workflow_id = message.workflow_id if message else getattr(ctx, "workflow_id", "")
        task_id = message.task_id if message else getattr(ctx, "task_id", "")
        claim = self._orchestrator.claim_completion(
            spec=IdempotencyInsertSpec(
                idempotency_key=key,
                workflow_id=workflow_id,
                task_id=task_id,
                result_artifact_id=handler_result.result_artifact_id,
            )
        )
        if claim.phase == IdempotencyPhase.DUPLICATE_REJECTED:
            if isinstance(ctx, DeliveryContext):
                self._scenario_c_loser_path(ctx=ctx, handler_result=handler_result)
            return
        expected = WorkflowStateGuard.expected_state_for_task(task_type)
        request = TransitionRequest(
            workflow_id=workflow_id,
            expected_state=expected,
            signal=handler_result.transition_signal or TransitionSignal.STAGE_COMPLETED,
            reason=handler_result.reason or "stage completed",
            completing_task_id=task_id,
            idempotency_key=key,
        )
        transition_result = self._workflow_engine.apply_transition(request)
        self._apply_dispatch_bridge_transitions(
            workflow_id=workflow_id,
            task_id=task_id,
            idempotency_key=key,
            transition_result=transition_result,
        )
        if task_id:
            self._workflow_repo.update_task(
                task_id,
                status=PersistenceTaskStatus.COMPLETED,
                completed_at=self._clock(),
            )

    def _apply_dispatch_bridge_transitions(
        self,
        *,
        workflow_id: str,
        task_id: str,
        idempotency_key: str,
        transition_result: TransitionResult,
    ) -> None:
        """Advance pause states to active execution states after outbox enqueue (WF HLD §4)."""
        pause_after_enqueue = frozenset(
            {
                WorkflowState.COLLECTED,
                WorkflowState.TOPIC_SELECTED,
                WorkflowState.SCENARIO_GENERATED,
            }
        )
        post_stage_bridge = frozenset(
            {
                WorkflowState.REVIEW_PASSED,
                WorkflowState.REVISION_REQUIRED,
            }
        )
        active_execution_states = frozenset(
            {
                WorkflowState.SELECTING_TOPIC,
                WorkflowState.GENERATING_SCENARIO,
                WorkflowState.REVIEWING,
                WorkflowState.AWAITING_HUMAN_APPROVAL,
            }
        )

        current = transition_result
        while True:
            needs_bridge = (
                current.enqueued_task is not None
                and current.to_state in pause_after_enqueue
            ) or current.to_state in post_stage_bridge
            if not needs_bridge:
                return
            current = self._workflow_engine.apply_transition(
                TransitionRequest(
                    workflow_id=workflow_id,
                    expected_state=current.to_state,
                    signal=TransitionSignal.STAGE_COMPLETED,
                    reason="dispatch_bridge",
                    completing_task_id=task_id,
                    idempotency_key=idempotency_key,
                )
            )
            if current.to_state in active_execution_states:
                return

    def _scenario_c_loser_path(
        self,
        *,
        ctx: DeliveryContext,
        handler_result: TaskHandlerResult,
    ) -> None:
        message = ctx.delivery.message
        workflow_record = self._workflow_repo.get_workflow(message.workflow_id)
        if workflow_record is None:
            return
        expected_post = WorkflowStateGuard.post_transition_state(
            ctx.task_type,
            handler_result.transition_signal or TransitionSignal.STAGE_COMPLETED,
        )
        current = to_workflow_state(workflow_record.state.value)
        if current == expected_post:
            resolution = DuplicateResolution.REJECTED_DURING_COMMIT
            self._recorded_resolutions.append(resolution.value)
            self.telemetry.record_duplicate(task_type=ctx.task_type, resolution=resolution)
            return
        try:
            expected = WorkflowStateGuard.expected_state_for_task(ctx.task_type)
            self._workflow_engine.apply_transition(
                TransitionRequest(
                    workflow_id=message.workflow_id,
                    expected_state=expected,
                    signal=handler_result.transition_signal or TransitionSignal.STAGE_COMPLETED,
                    reason="scenario_c_loser",
                    completing_task_id=message.task_id,
                    idempotency_key=ctx.idempotency_key,
                )
            )
        except WorkflowConflictError:
            reloaded = self._workflow_repo.get_workflow(message.workflow_id)
            if reloaded is not None and to_workflow_state(reloaded.state.value) == expected_post:
                resolution = DuplicateResolution.REJECTED_DURING_COMMIT
                self._recorded_resolutions.append(resolution.value)
                self.telemetry.record_duplicate(task_type=ctx.task_type, resolution=resolution)
                return
            raise
        task = self._workflow_repo.get_task(message.task_id)
        if task is not None and task.status != PersistenceTaskStatus.COMPLETED:
            self._workflow_repo.update_task(
                message.task_id,
                status=PersistenceTaskStatus.COMPLETED,
                completed_at=self._clock(),
            )

    def _handle_retryable_failure(
        self,
        *,
        task_record: TaskRecord,
        task_type: TaskType,
        effective_attempt: int,
        error_class: str,
        reason: str,
    ) -> None:
        with self._transaction_manager.transaction():
            self._workflow_repo.update_task(
                task_record.task_id,
                status=PersistenceTaskStatus.DISPATCHED,
                attempt=effective_attempt + 1,
                failure_reason=reason,
            )
        delay = self._retry_classifier.schedule_backoff(
            task_id=task_record.task_id,
            attempt=effective_attempt,
            task_type=task_type,
        )
        self.telemetry.record_retry(
            task_type=task_type,
            kind="infrastructure_retry",
            attempt=effective_attempt,
            backoff_seconds=delay,
        )
        self.telemetry.record_failure(
            task_type=task_type,
            error_class=error_class,
            retryable=True,
            workflow_id=task_record.workflow_id,
            task_id=task_record.task_id,
        )

    def _handle_permanent_failure(
        self,
        *,
        delivery: PendingDelivery,
        task_type: TaskType,
        task_record: TaskRecord,
        effective_attempt: int,
        error_class: str,
        exhausted: bool,
        skip_ack: bool,
        skip_transition: bool = False,
    ) -> None:
        if not skip_transition:
            signal = (
                TransitionSignal.RETRIES_EXHAUSTED
                if exhausted
                else TransitionSignal.UNRECOVERABLE_ERROR
            )
            with self._transaction_manager.transaction():
                self._transaction_guard.require_active(operation="fail_task")
                expected = WorkflowStateGuard.expected_state_for_task(task_type)
                self._workflow_engine.apply_transition(
                    TransitionRequest(
                        workflow_id=delivery.message.workflow_id,
                        expected_state=expected,
                        signal=signal,
                        reason=error_class,
                        completing_task_id=delivery.message.task_id,
                    )
                )
                status = (
                    PersistenceTaskStatus.DEAD_LETTER
                    if exhausted
                    else PersistenceTaskStatus.FAILED
                )
                self._workflow_repo.update_task(
                    task_record.task_id,
                    status=status,
                    failure_reason=error_class,
                )
        else:
            with self._transaction_manager.transaction():
                self._workflow_repo.update_task(
                    task_record.task_id,
                    status=PersistenceTaskStatus.FAILED,
                    failure_reason=error_class,
                )
        self._failure_injection.invoke_if_active(InjectionId.FINJ_WKR_PRE_ACK)
        if not skip_ack:
            self._task_queue.ack(delivery)
        self.telemetry.record_failure(
            task_type=task_type,
            error_class=error_class,
            retryable=False,
            workflow_id=delivery.message.workflow_id,
            task_id=delivery.message.task_id,
        )

    # --- Contract / unit test seams (LLD §12) ---

    def should_retry(self, attempt: int, max_attempts: int) -> bool:
        return attempt < max_attempts

    def classify(self, err: BaseException) -> tuple[bool, str]:
        return self._retry_classifier.classify_exception(err)

    def handle_exhausted_retry(self) -> None:
        delivery = self._make_test_delivery()
        task_record = self._ensure_test_task(delivery)
        self._handle_permanent_failure(
            delivery=delivery,
            task_type=delivery.message.task_type,
            task_record=task_record,
            effective_attempt=3,
            error_class="RETRIES_EXHAUSTED",
            exhausted=True,
            skip_ack=True,
        )

    def process_concurrent_workflows(self, count: int) -> list[str]:
        results: list[str] = []
        for index in range(count):
            wf_id = f"wf-concurrent-{index}"
            delivery = self._make_test_delivery(workflow_id=wf_id, task_id=f"task-{index}")
            self._ensure_test_task(delivery, workflow_id=wf_id)
            self._process_delivery(delivery, skip_ack=True)
            results.append(wf_id)
        return results

    def max_in_flight(self, task_type: TaskType) -> int:
        return self._concurrency_pool._limits.get(task_type, 1)  # type: ignore[attr-defined]

    def process_reuse_path(self) -> None:
        self.telemetry.record_retry(
            task_type=TaskType.GENERATE_SCENARIO,
            kind="infrastructure_reuse",
            attempt=2,
            backoff_seconds=0.0,
        )

    def short_circuit_precheck(self) -> None:
        resolution = DuplicateResolution.IGNORED_BEFORE_EXECUTION
        self._recorded_resolutions.append(resolution.value)
        self.telemetry.record_duplicate(
            task_type=TaskType.COLLECT,
            resolution=resolution,
        )

    def race_claim_completion(self, shared_repo: object) -> int:
        from persistence.types import IdempotencyInsertSpec

        orchestrator = DefaultIdempotencyOrchestrator(idempotency_repo=shared_repo)  # type: ignore[arg-type]
        spec = IdempotencyInsertSpec(
            idempotency_key="wf-race:COLLECT:1",
            workflow_id="wf-race",
            task_id="task-race-1",
            result_artifact_id="art-race",
        )
        winners = 0
        with self._transaction_manager.transaction():
            first = orchestrator.claim_completion(spec=spec)
            if first.phase == IdempotencyPhase.CLAIMED:
                winners += 1
        with self._transaction_manager.transaction():
            second = orchestrator.claim_completion(spec=spec)
            if second.phase == IdempotencyPhase.CLAIMED:
                winners += 1
        return winners

    def run_select_topic_success(self) -> None:
        delivery = self._make_test_delivery(task_type=TaskType.SELECT_TOPIC)
        self._seed_collected_stories(delivery.message.workflow_id)
        self._ensure_test_task(delivery, task_type=TaskType.SELECT_TOPIC)
        self._process_delivery(delivery, skip_ack=True)

    def process_with_injection_trace(self) -> list[InjectionId]:
        invoked: list[InjectionId] = []
        failure_injection = self._failure_injection
        original_invoke = failure_injection.invoke_if_active

        def tracked_invoke(injection_id: InjectionId) -> bool:
            active = original_invoke(injection_id)
            if active:
                invoked.append(injection_id)
            return active

        failure_injection.invoke_if_active = tracked_invoke  # type: ignore[method-assign]

        delivery = self._make_test_delivery(
            task_type=TaskType.SELECT_TOPIC,
            task_id="task-select-contract-1",
        )
        self._seed_collected_stories(delivery.message.workflow_id)
        self._ensure_test_task(delivery, task_type=TaskType.SELECT_TOPIC)
        expected = WorkflowStateGuard.expected_state_for_task(TaskType.SELECT_TOPIC)
        if hasattr(self._workflow_repo, "set_state"):
            self._workflow_repo.set_state(delivery.message.workflow_id, expected.value)  # type: ignore[attr-defined]
        self._process_delivery(delivery, skip_ack=False)
        return invoked

    def task_timing_boundaries(self) -> dict[str, object]:
        now = self._clock()
        return {
            "enqueued_at": now.isoformat(),
            "completed_at": now.isoformat(),
            "workflow_duration_ms": None,
            "workflow_state_duration_ms": None,
        }

    def recorded_completion_metrics(self) -> list[str]:
        if isinstance(self.telemetry, RecordingWorkerTelemetry):
            timing = TaskTiming(
                enqueued_at=self._clock() - timedelta(seconds=5),
                dequeued_at=self._clock(),
                handler_started_at=self._clock(),
                handler_finished_at=self._clock() + timedelta(seconds=1),
            )
            self.telemetry.record_completion(
                timing=timing,
                task_type=TaskType.COLLECT,
                duplicate_resolution=None,
            )
            return [str(e.get("name")) for e in self.telemetry.metric_events]
        return []

    def recorded_retry_kinds(self) -> list[str]:
        if isinstance(self.telemetry, RecordingWorkerTelemetry):
            self.telemetry.record_retry(
                task_type=TaskType.GENERATE_SCENARIO,
                kind="infrastructure_reuse",
                attempt=2,
                backoff_seconds=0.0,
            )
            self.telemetry.record_retry(
                task_type=TaskType.GENERATE_SCENARIO,
                kind="regeneration",
                attempt=1,
                backoff_seconds=0.0,
            )
            return list(self.telemetry.retry_kinds)
        return []

    def build_context(self) -> TaskExecutionContext:
        delivery = self._make_test_delivery()
        task_record = self._ensure_test_task(delivery)
        timing = TaskTiming(
            enqueued_at=delivery.message.created_at,
            dequeued_at=self._clock(),
        )
        return self._build_execution_context(
            delivery=delivery,
            task_record=task_record,
            idempotency_key="wf-contract-1:COLLECT:1",
            timing=timing,
        )

    def success_path_event_order(self) -> list[str]:
        self._event_order.clear()
        delivery = self._make_test_delivery()
        self._ensure_test_task(delivery)
        self._process_delivery(delivery, skip_ack=False)
        return list(self._event_order)

    def _make_test_delivery(
        self,
        *,
        workflow_id: str = "wf-contract-1",
        task_id: str = "task-contract-1",
        task_type: TaskType = TaskType.COLLECT,
    ) -> PendingDelivery:
        from task_queue import PendingDelivery, TaskMessage

        now = self._clock()
        return PendingDelivery(
            message=TaskMessage(
                task_id=task_id,
                workflow_id=workflow_id,
                task_type=task_type,
                attempt=1,
                created_at=now,
                payload_reference="ref://payload/contract-1",
            ),
            stream=self._loop_config.stream,
            consumer_group=self._loop_config.consumer_group,
            delivery_id=f"del-{task_id}",
            dequeued_at=now,
        )

    def _ensure_test_task(
        self,
        delivery: PendingDelivery,
        *,
        workflow_id: str | None = None,
        task_type: TaskType | None = None,
    ) -> TaskRecord:
        from persistence.types import PayloadReference, TaskType as PersTaskType

        wf_id = workflow_id or delivery.message.workflow_id
        tt = task_type or delivery.message.task_type
        pers_type = PersTaskType(tt.value)
        existing_wf = self._workflow_repo.get_workflow(wf_id)
        if existing_wf is None:
            from persistence.types import WorkflowState as PersWorkflowState

            expected = WorkflowStateGuard.expected_state_for_task(tt)
            self._workflow_repo.create_workflow(
                wf_id,
                initial_state=PersWorkflowState(expected.value),
            )
        existing_task = self._workflow_repo.get_task(delivery.message.task_id)
        if existing_task is not None:
            return existing_task
        now = self._clock()
        from persistence.types import TaskRecord, TaskStatus

        task = TaskRecord(
            task_id=delivery.message.task_id,
            workflow_id=wf_id,
            task_type=pers_type,
            attempt=delivery.message.attempt,
            status=TaskStatus.DISPATCHED,
            payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
            idempotency_key="idem-1",
            created_at=now,
            updated_at=now,
        )
        if hasattr(self._workflow_repo, "upsert_task"):
            return self._workflow_repo.upsert_task(task)  # type: ignore[no-any-return]
        with self._transaction_manager.transaction():
            return self._workflow_repo.create_task(task)

    def _seed_collected_stories(self, workflow_id: str) -> None:
        from persistence.types import ArtifactCreateSpec, ArtifactType

        with self._transaction_manager.transaction():
            self._artifact_repo.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.COLLECTED_STORIES,
                    name="collected_stories",
                    version=1,
                    logical_version=1,
                    content={
                        "schema_version": 1,
                        "candidates": [
                            {
                                "source_id": "hn-1",
                                "title": "Test",
                                "url": "https://example.com",
                                "score": 10,
                                "comment_count": 1,
                            }
                        ],
                    },
                )
            )


def create_worker_loop(
    *,
    config: AppConfig,
    loop_config: WorkerLoopConfig,
    registry: DefaultTaskHandlerRegistry,
    task_queue: TaskQueue,
    task_lease_repo: TaskLeaseRepo,
    workflow_engine: WorkflowEngine,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    idempotency_orchestrator: DefaultIdempotencyOrchestrator,
    transaction_manager: TransactionManager,
    failure_injection: object,
    collector: object,
    topic_selection_agent: object,
    scenario_generation_agent: object,
    critic_agent: object,
    model_provider_factory: Callable,
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
) -> DefaultWorkerLoop:
    return DefaultWorkerLoop(
        config=config,
        loop_config=loop_config,
        registry=registry,
        task_queue=task_queue,
        task_lease_repo=task_lease_repo,
        workflow_engine=workflow_engine,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_orchestrator=idempotency_orchestrator,
        transaction_manager=transaction_manager,
        failure_injection=failure_injection,
        collector=collector,
        topic_selection_agent=topic_selection_agent,
        scenario_generation_agent=scenario_generation_agent,
        critic_agent=critic_agent,
        model_provider_factory=model_provider_factory,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )


def run_task_loop(
    *,
    config: AppConfig,
    loop_config: WorkerLoopConfig,
    registry: DefaultTaskHandlerRegistry,
    task_queue: TaskQueue,
    task_lease_repo: TaskLeaseRepo,
    workflow_engine: WorkflowEngine,
    workflow_repo: WorkflowRepo,
    artifact_repo: ArtifactRepo,
    idempotency_orchestrator: DefaultIdempotencyOrchestrator,
    transaction_manager: TransactionManager,
    failure_injection: object,
    collector: object,
    topic_selection_agent: object,
    scenario_generation_agent: object,
    critic_agent: object,
    model_provider_factory: Callable,
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
) -> None:
    loop = create_worker_loop(
        config=config,
        loop_config=loop_config,
        registry=registry,
        task_queue=task_queue,
        task_lease_repo=task_lease_repo,
        workflow_engine=workflow_engine,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_orchestrator=idempotency_orchestrator,
        transaction_manager=transaction_manager,
        failure_injection=failure_injection,
        collector=collector,
        topic_selection_agent=topic_selection_agent,
        scenario_generation_agent=scenario_generation_agent,
        critic_agent=critic_agent,
        model_provider_factory=model_provider_factory,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )
    try:
        loop.run()
    except WorkerShutdownError:
        raise
    finally:
        loop.stop()
