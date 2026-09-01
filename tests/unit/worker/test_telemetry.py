"""Pre-code test mold for WKR-008 — WorkerTelemetry (LLD §4.10, §11)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Iterator

import pytest

from config.types import TaskType
from worker import DuplicateResolution, TaskTiming

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


@contextmanager
def _observability_fakes() -> Iterator[tuple[object, object, object]]:
    from observability import get_logger, get_meter, get_tracer
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="worker-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    yield get_logger(), get_meter(), get_tracer()
    _reset_observability_state()


def _timing() -> TaskTiming:
    enqueued = _FIXED_NOW - timedelta(seconds=5)
    dequeued = _FIXED_NOW
    started = _FIXED_NOW + timedelta(milliseconds=10)
    finished = _FIXED_NOW + timedelta(seconds=2)
    return TaskTiming(
        enqueued_at=enqueued,
        dequeued_at=dequeued,
        handler_started_at=started,
        handler_finished_at=finished,
    )


def test_recording_telemetry_captures_metric_increments() -> None:
    from worker.telemetry import RecordingWorkerTelemetry

    with _observability_fakes() as (logger, meter, tracer):
        telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        telemetry.record_duplicate(
            task_type=TaskType.COLLECT,
            resolution=DuplicateResolution.IGNORED_BEFORE_EXECUTION,
        )
        assert telemetry.metric_events  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("042")
def test_record_completion_distinct_queue_wait_and_execution() -> None:
    """WKR-TC-042: queue wait and execution recorded as separate histograms."""
    from worker.constants import METRIC_EXECUTION, METRIC_QUEUE_WAIT
    from worker.telemetry import RecordingWorkerTelemetry

    with _observability_fakes() as (logger, meter, tracer):
        telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        telemetry.record_completion(
            timing=_timing(),
            task_type=TaskType.SELECT_TOPIC,
            duplicate_resolution=None,
        )
        names = {event["name"] for event in telemetry.metric_events}  # type: ignore[attr-defined]
        assert METRIC_QUEUE_WAIT in names
        assert METRIC_EXECUTION in names
        assert METRIC_QUEUE_WAIT != METRIC_EXECUTION


@pytest.mark.wkr_tc("015")
def test_record_duplicate_ignored_before_execution() -> None:
    """WKR-TC-015 seam: duplicate metric with IGNORED_BEFORE_EXECUTION resolution."""
    from worker.constants import METRIC_DUPLICATE
    from worker.telemetry import RecordingWorkerTelemetry

    with _observability_fakes() as (logger, meter, tracer):
        telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        telemetry.record_duplicate(
            task_type=TaskType.GENERATE_SCENARIO,
            resolution=DuplicateResolution.IGNORED_BEFORE_EXECUTION,
        )
        duplicate_events = [
            e for e in telemetry.metric_events if e["name"] == METRIC_DUPLICATE  # type: ignore[attr-defined]
        ]
        assert duplicate_events
        assert duplicate_events[0]["labels"]["resolution"] == DuplicateResolution.IGNORED_BEFORE_EXECUTION.value


@pytest.mark.wkr_tc("043")
def test_record_retry_kind_labels_distinct() -> None:
    """WKR-TC-043: infrastructure_reuse vs regeneration distinct kind labels."""
    from worker.constants import METRIC_RETRY
    from worker.telemetry import RecordingWorkerTelemetry

    with _observability_fakes() as (logger, meter, tracer):
        telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        telemetry.record_retry(
            task_type=TaskType.GENERATE_SCENARIO,
            kind="infrastructure_reuse",
            attempt=2,
            backoff_seconds=1.0,
        )
        telemetry.record_retry(
            task_type=TaskType.GENERATE_SCENARIO,
            kind="regeneration",
            attempt=1,
            backoff_seconds=0.0,
        )
        kinds = {
            e["labels"]["kind"]
            for e in telemetry.metric_events  # type: ignore[attr-defined]
            if e["name"] == METRIC_RETRY
        }
        assert kinds == {"infrastructure_reuse", "regeneration"}


def test_forbidden_log_fields_not_in_structured_payload() -> None:
    """MOD-WKR-INV-022: telemetry logs must not include prompt/response/api_key."""
    from worker.constants import FORBIDDEN_LOG_FIELDS, LOG_TASK_STARTED
    from worker.telemetry import RecordingWorkerTelemetry

    with _observability_fakes() as (logger, meter, tracer):
        telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)
        telemetry.record_task_started(
            workflow_id="wf-1",
            task_id="task-1",
            task_type=TaskType.COLLECT,
            attempt=1,
        )
        for event in telemetry.log_events:  # type: ignore[attr-defined]
            if event.get("event") == LOG_TASK_STARTED:
                payload_keys = set(event.get("fields", {}).keys())
                assert payload_keys.isdisjoint(FORBIDDEN_LOG_FIELDS)
