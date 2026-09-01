"""Outbox publisher loop — persistence outbox to task queue (LLD §11)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Transactional outbox — state changes and task enqueue
# intent are committed atomically in PostgreSQL; this loop publishes to Redis reliably.

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from config.types import AppConfig, InjectionId, TaskType
from failure_injection.protocols import FailureInjectionRegistry
from observability import get_correlation_context
from persistence.protocols import OutboxRepo, WorkflowRepo
from persistence.types import OutboxEntry
from task_queue.errors import (
    InvalidTaskMessageError,
    TaskQueueConnectionError,
    TaskQueueUnavailableError,
)
from task_queue.protocols import TaskQueue
from task_queue.types import TaskMessage

from .constants import (
    OUTBOX_RETRY_INITIAL_SECONDS,
    OUTBOX_RETRY_MAX_ATTEMPTS,
    OUTBOX_RETRY_MAX_SECONDS,
    WORKER_STREAM_BY_TASK_TYPE,
)
from .protocols import OutboxPublisherLoop
from .telemetry import RuntimeTelemetry
from .types import OutboxPublishBatchResult, OutboxPublisherConfig

if TYPE_CHECKING:
    from observability.protocols import Logger, Meter, Tracer
    from workflow.protocols import WorkflowEngine


class OutboxPublishPermanentError(Exception):
    """Non-retryable outbox publish failure."""


class OutboxPublishTransientError(Exception):
    """Retryable outbox publish failure after exhausting attempts."""


@dataclass
class OutboxPublishFrame:
    """Mutable per-entry publish attempt (internal)."""

    entry: OutboxEntry
    stream: str
    message: TaskMessage | None = None
    enqueue_attempts: int = 0
    mark_attempts: int = 0
    last_error_class: str | None = None


def outbox_retry_schedule(
    *,
    initial_seconds: float,
    max_seconds: float,
    max_attempts: int,
) -> tuple[float, ...]:
    """Exponential backoff delays capped at max_seconds."""
    delays: list[float] = []
    delay = initial_seconds
    for _ in range(max_attempts):
        delays.append(min(delay, max_seconds))
        delay *= 2.0
    return tuple(delays)


def _sleep_backoff(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _enqueue_with_retry(
    frame: OutboxPublishFrame,
    *,
    queue: TaskQueue,
    outbox_repo: OutboxRepo | None = None,
    initial_seconds: float = OUTBOX_RETRY_INITIAL_SECONDS,
    max_seconds: float = OUTBOX_RETRY_MAX_SECONDS,
    max_attempts: int = OUTBOX_RETRY_MAX_ATTEMPTS,
) -> None:
    del outbox_repo  # mark_published must never run from enqueue path
    if frame.message is None:
        raise OutboxPublishPermanentError("message not built")

    schedule = outbox_retry_schedule(
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
        max_attempts=max_attempts,
    )
    last_error: BaseException | None = None

    for attempt_index, delay in enumerate(schedule):
        try:
            queue.enqueue(frame.stream, frame.message)
            return
        except InvalidTaskMessageError as exc:
            frame.last_error_class = exc.__class__.__name__
            raise OutboxPublishPermanentError(str(exc)) from exc
        except (TaskQueueConnectionError, TaskQueueUnavailableError, RuntimeError) as exc:
            frame.enqueue_attempts += 1
            frame.last_error_class = exc.__class__.__name__
            last_error = exc
            if attempt_index < len(schedule) - 1:
                _sleep_backoff(delay)

    raise OutboxPublishTransientError(
        frame.last_error_class or "enqueue_failed",
    ) from last_error


def _mark_published_with_retry(
    frame: OutboxPublishFrame,
    *,
    repo: OutboxRepo,
    clock: Callable[[], datetime] | None = None,
    initial_seconds: float = OUTBOX_RETRY_INITIAL_SECONDS,
    max_seconds: float = OUTBOX_RETRY_MAX_SECONDS,
    max_attempts: int = OUTBOX_RETRY_MAX_ATTEMPTS,
) -> None:
    now = (clock or (lambda: datetime.now(UTC)))()
    schedule = outbox_retry_schedule(
        initial_seconds=initial_seconds,
        max_seconds=max_seconds,
        max_attempts=max_attempts,
    )
    last_error: BaseException | None = None

    for attempt_index, delay in enumerate(schedule):
        try:
            repo.mark_published(frame.entry.outbox_id, published_at=now)
            return
        except (TaskQueueConnectionError, TaskQueueUnavailableError, RuntimeError) as exc:
            frame.mark_attempts += 1
            frame.last_error_class = exc.__class__.__name__
            last_error = exc
            if attempt_index < len(schedule) - 1:
                _sleep_backoff(delay)

    raise OutboxPublishTransientError(
        frame.last_error_class or "mark_published_failed",
    ) from last_error


def resolve_outbox_stream(entry: OutboxEntry) -> str:
    task_type = TaskType(entry.task_type.value)
    return WORKER_STREAM_BY_TASK_TYPE[task_type]


class OutboxMessageBuilder:
    """Maps unpublished outbox rows to task queue messages."""

    def __init__(
        self,
        *,
        workflow_repo: WorkflowRepo,
        tracer: object | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        del tracer
        self._workflow_repo = workflow_repo
        self._clock = clock or (lambda: datetime.now(UTC))

    def build(self, entry: OutboxEntry) -> TaskMessage:
        task = self._workflow_repo.get_task(entry.task_id)
        if task is None:
            raise OutboxPublishPermanentError(f"task not found: {entry.task_id}")

        carrier: dict[str, str] = {}
        get_correlation_context().inject(carrier)

        return TaskMessage(
            task_id=entry.task_id,
            workflow_id=entry.workflow_id,
            task_type=TaskType(entry.task_type.value),
            attempt=task.attempt,
            created_at=task.created_at,
            payload_reference=entry.payload_reference.ref_id,
            trace_carrier=carrier,
        )


class DefaultOutboxPublisherLoop:
    """Coordinator loop publishing outbox rows to the task queue."""

    def __init__(
        self,
        *,
        config: AppConfig,
        publisher_config: OutboxPublisherConfig,
        outbox_repo: OutboxRepo,
        workflow_repo: WorkflowRepo,
        task_queue: TaskQueue,
        failure_injection: FailureInjectionRegistry,
        message_builder: OutboxMessageBuilder,
        telemetry: RuntimeTelemetry,
        shutdown: threading.Event,
        workflow_engine: WorkflowEngine | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        del config, workflow_repo, workflow_engine
        self._publisher_config = publisher_config
        self._outbox_repo = outbox_repo
        self._task_queue = task_queue
        self._failure_injection = failure_injection
        self._message_builder = message_builder
        self._telemetry = telemetry
        self._shutdown = shutdown
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stopped = False

    def run(self) -> None:
        while not self._shutdown.is_set():
            result = self._publish_batch()
            self._telemetry.emit_outbox_batch(result)
            self._sleep_interruptible(self._publisher_config.poll_interval_seconds)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._shutdown.set()

    def _sleep_interruptible(self, seconds: float) -> None:
        self._shutdown.wait(timeout=seconds)

    def _publish_batch(self) -> OutboxPublishBatchResult:
        rows = self._outbox_repo.fetch_unpublished(limit=self._publisher_config.batch_size)
        published_count = 0
        failed_count = 0
        skipped_count = 0

        for entry in rows:
            try:
                frame = OutboxPublishFrame(
                    entry=entry,
                    stream=resolve_outbox_stream(entry),
                )
                frame.message = self._message_builder.build(entry)
                self._failure_injection.invoke_if_active(InjectionId.FINJ_COORD_DISPATCH)
                _enqueue_with_retry(frame, queue=self._task_queue)
                _mark_published_with_retry(frame, repo=self._outbox_repo, clock=self._clock)
                published_count += 1
            except OutboxPublishPermanentError:
                failed_count += 1
            except OutboxPublishTransientError:
                failed_count += 1

        return OutboxPublishBatchResult(
            fetched_count=len(rows),
            published_count=published_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
        )


def create_outbox_publisher_loop(
    *,
    config: AppConfig,
    publisher_config: OutboxPublisherConfig,
    outbox_repo: OutboxRepo,
    workflow_repo: WorkflowRepo,
    task_queue: TaskQueue,
    workflow_engine: WorkflowEngine,
    failure_injection: FailureInjectionRegistry,
    logger: Logger,
    meter: Meter,
    tracer: Tracer,
    shutdown: threading.Event | None = None,
) -> OutboxPublisherLoop:
    """Build DefaultOutboxPublisherLoop with OutboxMessageBuilder."""
    from .types import ProcessKind

    telemetry = RuntimeTelemetry(
        logger=logger,
        meter=meter,
        process_kind=ProcessKind.COORDINATOR,
    )
    builder = OutboxMessageBuilder(workflow_repo=workflow_repo, tracer=tracer)
    event = shutdown or threading.Event()
    return DefaultOutboxPublisherLoop(
        config=config,
        publisher_config=publisher_config,
        outbox_repo=outbox_repo,
        workflow_repo=workflow_repo,
        task_queue=task_queue,
        failure_injection=failure_injection,
        message_builder=builder,
        telemetry=telemetry,
        shutdown=event,
        workflow_engine=workflow_engine,
    )
