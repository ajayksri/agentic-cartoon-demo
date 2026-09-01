"""Worker telemetry (LLD §4.10, §11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from config.types import TaskType
from observability.protocols import Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor

from .constants import (
    FORBIDDEN_LOG_FIELDS,
    LOG_DUPLICATE,
    LOG_LEASE_CONFLICT,
    LOG_RETRY,
    LOG_STALE,
    LOG_TASK_COMPLETED,
    LOG_TASK_FAILED,
    LOG_TASK_STARTED,
    METRIC_DUPLICATE,
    METRIC_EXECUTION,
    METRIC_FAILURE,
    METRIC_QUEUE_WAIT,
    METRIC_RETRY,
    SPAN_HANDLE_TASK,
)
from .types import DuplicateResolution, TaskTiming


class WorkerTelemetry:
    """Metrics, logs, and spans for worker task processing."""

    def __init__(self, *, logger: Logger, meter: Meter, tracer: Tracer) -> None:
        self._logger = logger
        self._meter = meter
        self._tracer = tracer
        self._queue_wait_hist: object | None = None
        self._execution_hist: object | None = None
        self._duplicate_counter: object | None = None
        self._retry_counter: object | None = None
        self._failure_counter: object | None = None

    def _histogram(self, logical_name: str) -> object:
        descriptor = MetricDescriptor(
            logical_name=logical_name,
            metric_type="histogram",
            unit="ms",
            description=logical_name,
            allowed_label_keys=frozenset({"task_type"}),
        )
        return self._meter.register_histogram(descriptor)

    def _counter(self, logical_name: str, label_keys: frozenset[str]) -> object:
        descriptor = MetricDescriptor(
            logical_name=logical_name,
            metric_type="counter",
            unit="1",
            description=logical_name,
            allowed_label_keys=label_keys,
        )
        return self._meter.register_counter(descriptor)

    def _ensure_instruments(self) -> None:
        if self._queue_wait_hist is None:
            self._queue_wait_hist = self._histogram(METRIC_QUEUE_WAIT)
            self._execution_hist = self._histogram(METRIC_EXECUTION)
            self._duplicate_counter = self._counter(
                METRIC_DUPLICATE,
                frozenset({"task_type", "resolution"}),
            )
            self._retry_counter = self._counter(
                METRIC_RETRY,
                frozenset({"task_type", "kind"}),
            )
            self._failure_counter = self._counter(
                METRIC_FAILURE,
                frozenset({"task_type", "error_class"}),
            )

    def record_task_started(
        self,
        *,
        workflow_id: str,
        task_id: str,
        task_type: TaskType,
        attempt: int,
        trace_carrier: dict[str, str] | None = None,
    ) -> Span:
        self._ensure_instruments()
        span = self._tracer.start_span(SPAN_HANDLE_TASK)
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("task_type", task_type.value)
        span.set_attribute("attempt", attempt)
        self._safe_log(
            LOG_TASK_STARTED,
            "Task started",
            workflow_id=workflow_id,
            task_id=task_id,
            task_type=task_type.value,
            attempt=attempt,
        )
        return span

    def record_completion(
        self,
        *,
        timing: TaskTiming,
        task_type: TaskType,
        duplicate_resolution: DuplicateResolution | None,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self._ensure_instruments()
        queue_wait_ms = _duration_ms(timing.enqueued_at, timing.dequeued_at)
        self._queue_wait_hist.record(  # type: ignore[union-attr]
            queue_wait_ms,
            labels={"task_type": task_type.value},
        )
        if timing.handler_started_at and timing.handler_finished_at:
            execution_ms = _duration_ms(
                timing.handler_started_at,
                timing.handler_finished_at,
            )
            self._execution_hist.record(  # type: ignore[union-attr]
                execution_ms,
                labels={"task_type": task_type.value},
            )
        fields: dict[str, str | int | float | bool] = {
            "task_type": task_type.value,
        }
        if workflow_id is not None:
            fields["workflow_id"] = workflow_id
        if task_id is not None:
            fields["task_id"] = task_id
        if duplicate_resolution is not None:
            fields["duplicate_resolution"] = duplicate_resolution.value
        if workflow_id is not None:
            self._safe_log(LOG_TASK_COMPLETED, "Task completed", **fields)

    def record_duplicate(
        self,
        *,
        task_type: TaskType,
        resolution: DuplicateResolution,
    ) -> None:
        self._ensure_instruments()
        self._duplicate_counter.add(  # type: ignore[union-attr]
            1.0,
            labels={
                "task_type": task_type.value,
                "resolution": resolution.value,
            },
        )
        self._safe_log(
            LOG_DUPLICATE,
            "Duplicate detected",
            task_type=task_type.value,
            resolution=resolution.value,
        )

    def record_retry(
        self,
        *,
        task_type: TaskType,
        kind: Literal[
            "infrastructure_retry",
            "infrastructure_reuse",
            "regeneration",
        ],
        attempt: int,
        backoff_seconds: float,
    ) -> None:
        self._ensure_instruments()
        self._retry_counter.add(  # type: ignore[union-attr]
            1.0,
            labels={"task_type": task_type.value, "kind": kind},
        )
        self._safe_log(
            LOG_RETRY,
            "Retry scheduled",
            task_type=task_type.value,
            kind=kind,
            attempt=attempt,
            backoff_seconds=backoff_seconds,
        )

    def record_failure(
        self,
        *,
        task_type: TaskType,
        error_class: str,
        retryable: bool,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self._ensure_instruments()
        self._failure_counter.add(  # type: ignore[union-attr]
            1.0,
            labels={"task_type": task_type.value, "error_class": error_class},
        )
        fields: dict[str, str | int | float | bool] = {
            "task_type": task_type.value,
            "error_class": error_class,
            "retryable": retryable,
        }
        if workflow_id is not None:
            fields["workflow_id"] = workflow_id
        if task_id is not None:
            fields["task_id"] = task_id
        self._safe_log(
            LOG_TASK_FAILED,
            "Task failed",
            **fields,
        )

    def record_stale_ignored(
        self,
        *,
        reason: str,
        workflow_id: str,
        task_id: str,
    ) -> None:
        self._safe_log(
            LOG_STALE,
            "Stale task ignored",
            reason=reason,
            workflow_id=workflow_id,
            task_id=task_id,
        )

    def record_lease_conflict(self, *, task_id: str, worker_id: str) -> None:
        self._safe_log(
            LOG_LEASE_CONFLICT,
            "Lease conflict",
            task_id=task_id,
            worker_id=worker_id,
        )

    def _safe_log(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        filtered = {
            key: value
            for key, value in fields.items()
            if key not in FORBIDDEN_LOG_FIELDS
        }
        self._logger.info(event, message, **filtered)


class RecordingWorkerTelemetry(WorkerTelemetry):
    """Test subclass capturing metric and log events."""

    def __init__(self, *, logger: Logger, meter: Meter, tracer: Tracer) -> None:
        super().__init__(logger=logger, meter=meter, tracer=tracer)
        self.metric_events: list[dict[str, object]] = []
        self.log_events: list[dict[str, object]] = []
        self.retry_kinds: list[str] = []

    def record_duplicate(
        self,
        *,
        task_type: TaskType,
        resolution: DuplicateResolution,
    ) -> None:
        self.metric_events.append(
            {
                "name": METRIC_DUPLICATE,
                "labels": {
                    "task_type": task_type.value,
                    "resolution": resolution.value,
                },
            }
        )
        super().record_duplicate(task_type=task_type, resolution=resolution)

    def record_retry(
        self,
        *,
        task_type: TaskType,
        kind: Literal[
            "infrastructure_retry",
            "infrastructure_reuse",
            "regeneration",
        ],
        attempt: int,
        backoff_seconds: float,
    ) -> None:
        self.metric_events.append(
            {
                "name": METRIC_RETRY,
                "labels": {"task_type": task_type.value, "kind": kind},
            }
        )
        self.retry_kinds.append(kind)
        super().record_retry(
            task_type=task_type,
            kind=kind,
            attempt=attempt,
            backoff_seconds=backoff_seconds,
        )

    def record_completion(
        self,
        *,
        timing: TaskTiming,
        task_type: TaskType,
        duplicate_resolution: DuplicateResolution | None,
    ) -> None:
        queue_wait_ms = _duration_ms(timing.enqueued_at, timing.dequeued_at)
        self.metric_events.append(
            {
                "name": METRIC_QUEUE_WAIT,
                "labels": {"task_type": task_type.value},
                "value": queue_wait_ms,
            }
        )
        if timing.handler_started_at and timing.handler_finished_at:
            execution_ms = _duration_ms(
                timing.handler_started_at,
                timing.handler_finished_at,
            )
            self.metric_events.append(
                {
                    "name": METRIC_EXECUTION,
                    "labels": {"task_type": task_type.value},
                    "value": execution_ms,
                }
            )
        super().record_completion(
            timing=timing,
            task_type=task_type,
            duplicate_resolution=duplicate_resolution,
        )

    def record_task_started(
        self,
        *,
        workflow_id: str,
        task_id: str,
        task_type: TaskType,
        attempt: int,
        trace_carrier: dict[str, str] | None = None,
    ) -> Span:
        self.log_events.append(
            {
                "event": LOG_TASK_STARTED,
                "fields": {
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                    "task_type": task_type.value,
                    "attempt": attempt,
                },
            }
        )
        return super().record_task_started(
            workflow_id=workflow_id,
            task_id=task_id,
            task_type=task_type,
            attempt=attempt,
            trace_carrier=trace_carrier,
        )


def _duration_ms(start: datetime, end: datetime) -> float:
    delta = end - start
    return delta.total_seconds() * 1000.0
