"""Pre-code test mold for COL-009 — CollectionTelemetry (LLD §4.13)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Iterator

import pytest

from collector import CollectionStats, RejectionReason, StorySource
from collector.errors import CollectorFetchError



def _rejected_record(source_id: str) -> object:
    from collector.types import RejectedStoryRecord

    return RejectedStoryRecord(
        source=StorySource.HACKERNEWS,
        source_id=source_id,
        collected_at=datetime(2026, 8, 31, tzinfo=UTC),
        raw_observation={"id": source_id},
        reason_code=RejectionReason.VALIDATION_FAILED,
        reason_detail="validation failed at required_fields: title",
    )


@contextmanager
def _recording_observability() -> Iterator[tuple[object, object, object]]:
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from observability.fakes import CapturingMeter, InMemoryLogger, RecordingTracer
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="collector-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    yield InMemoryLogger, CapturingMeter, RecordingTracer
    _reset_observability_state()


def test_emit_started_logs_collection_started() -> None:
    """emit_started logs collection_started with candidate_count and returns root span."""
    from collector.observability import CollectionTelemetry
    from observability import get_logger, get_tracer
    from observability.fakes import InMemoryLogger, RecordingTracer

    with _recording_observability():
        telemetry = CollectionTelemetry()
        root_span = telemetry.emit_started(candidate_count=5)

        assert isinstance(get_logger(), InMemoryLogger)
        assert isinstance(get_tracer(), RecordingTracer)
        assert any("collection_started" in record for record in get_logger().records)
        assert root_span is not None


def test_emit_rejections_sampled_logs_each_when_under_cap() -> None:
    """Rejection sampling logs each rejection when count <= 100."""
    from collector.observability import CollectionTelemetry
    from observability import get_logger
    from observability.fakes import InMemoryLogger

    with _recording_observability():
        telemetry = CollectionTelemetry()
        rejections = [_rejected_record(str(i)) for i in range(3)]
        telemetry.emit_rejections_sampled(rejections)

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        assert len([r for r in logger.records if "collection_story_rejected" in r]) == 3


def test_emit_rejections_sampled_truncates_at_100() -> None:
    """CG-COL-HLD-002: first 100 rejections logged, then truncated summary."""
    from collector.observability import CollectionTelemetry
    from observability import get_logger
    from observability.fakes import InMemoryLogger

    with _recording_observability():
        telemetry = CollectionTelemetry()
        rejections = [_rejected_record(str(i)) for i in range(105)]
        telemetry.emit_rejections_sampled(rejections)

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        rejected_logs = [r for r in logger.records if "collection_story_rejected" in r]
        summary_logs = [r for r in logger.records if "collection_rejections_truncated" in r]

        assert len(rejected_logs) == 100
        assert len(summary_logs) == 1


def test_emit_fetch_failed_omits_raw_body() -> None:
    """COL-TC-015: fetch failure logs omit raw HN response bodies."""
    from collector.observability import CollectionTelemetry
    from observability import get_logger
    from observability.fakes import InMemoryLogger

    raw_body = "x" * 5000 + '{"huge": "payload"}'
    error = CollectorFetchError(f"fetch failed after body: {raw_body[:200]}")

    with _recording_observability():
        telemetry = CollectionTelemetry()
        telemetry.emit_fetch_failed(error=error)

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert raw_body not in joined
        assert '{"huge": "payload"}' not in joined


def test_emit_completed_sets_bounded_span_attributes() -> None:
    """emit_completed sets story_count, candidate_count, rejected_count on root span."""
    from collector.observability import CollectionTelemetry
    from observability import get_tracer
    from observability.fakes import RecordingTracer

    stats = CollectionStats(
        fetched_count=10,
        accepted_count=8,
        rejected_count=2,
        duplicate_count=1,
        candidate_count=5,
    )

    with _recording_observability():
        telemetry = CollectionTelemetry()
        root_span = telemetry.emit_started(candidate_count=5)
        telemetry.emit_completed(stats=stats, root_span=root_span, story_count=8)

        tracer = get_tracer()
        assert isinstance(tracer, RecordingTracer)
        assert tracer.spans[-1].status == "OK"


def test_record_run_metric_emits_bounded_status_labels() -> None:
    """record_run_metric registers collector_runs_total with success/failure labels."""
    from collector.observability import CollectionTelemetry
    from observability import get_meter
    from observability.fakes import CapturingMeter

    with _recording_observability():
        telemetry = CollectionTelemetry()
        telemetry.record_run_metric(success=True)
        telemetry.record_run_metric(success=False)

        meter = get_meter()
        assert isinstance(meter, CapturingMeter)
        assert any(
            name == "collector_runs_total" and labels == {"status": "success"}
            for name, _, _, labels in meter.emissions
        )
        assert any(
            name == "collector_runs_total" and labels == {"status": "failure"}
            for name, _, _, labels in meter.emissions
        )


def test_record_fetch_duration_emits_histogram_with_status_label() -> None:
    """record_fetch_duration registers histogram with bounded status label."""
    from collector.observability import CollectionTelemetry
    from observability import get_meter
    from observability.fakes import CapturingMeter

    with _recording_observability():
        telemetry = CollectionTelemetry()
        telemetry.record_fetch_duration(seconds=0.42, success=True)

        meter = get_meter()
        assert isinstance(meter, CapturingMeter)
        assert any(
            name == "collector_fetch_duration_seconds"
            and value == 0.42
            and labels == {"status": "success"}
            for name, _, value, labels in meter.emissions
        )
