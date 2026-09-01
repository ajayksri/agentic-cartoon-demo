"""Collection lifecycle telemetry seam."""

from __future__ import annotations

from collections.abc import Sequence

from observability import get_logger, get_meter, get_tracer
from observability.protocols import Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor

from collector.constants import REJECTION_LOG_SAMPLE_LIMIT
from collector.errors import CollectorError
from collector.types import CollectionStats, RejectedStoryRecord, RejectionReason


class CollectionTelemetry:
    def __init__(
        self,
        *,
        logger: Logger | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self._logger = logger
        self._tracer = tracer
        self._meter = meter

    def emit_started(self, *, candidate_count: int) -> Span:
        logger = self._logger or get_logger()
        tracer = self._tracer or get_tracer()

        logger.info(
            "collection_started",
            "collection run started",
            candidate_count=candidate_count,
        )
        span = tracer.start_span("collector.collect_stories")
        span.__enter__()
        return span

    def emit_completed(
        self,
        *,
        stats: CollectionStats,
        root_span: Span,
        story_count: int,
    ) -> None:
        logger = self._logger or get_logger()

        logger.info(
            "collection_completed",
            "collection run completed",
            fetched_count=stats.fetched_count,
            accepted_count=stats.accepted_count,
            rejected_count=stats.rejected_count,
            duplicate_count=stats.duplicate_count,
            candidate_count=stats.candidate_count,
        )
        root_span.set_attribute("story_count", story_count)
        root_span.set_attribute("candidate_count", stats.candidate_count)
        root_span.set_attribute("rejected_count", stats.rejected_count)
        root_span.end()
        root_span.__exit__(None, None, None)

    def emit_fetch_failed(self, *, error: CollectorError) -> None:
        logger = self._logger or get_logger()
        logger.error(
            "collection_fetch_failed",
            str(error),
            error_class=error.__class__.__name__,
            code=error.code,
            retryable=error.retryable,
        )

    def emit_story_rejected(self, *, source_id: str, reason_code: RejectionReason) -> None:
        logger = self._logger or get_logger()
        logger.warning(
            "collection_story_rejected",
            "story rejected during collection",
            source_id=source_id,
            reason_code=str(reason_code),
        )

    def emit_rejections_sampled(self, rejections: Sequence[RejectedStoryRecord]) -> None:
        logger = self._logger or get_logger()
        total = len(rejections)
        sample = rejections[:REJECTION_LOG_SAMPLE_LIMIT]

        for record in sample:
            self.emit_story_rejected(
                source_id=record.source_id,
                reason_code=record.reason_code,
            )

        if total > REJECTION_LOG_SAMPLE_LIMIT:
            logger.info(
                "collection_rejections_truncated",
                "rejection log sampling truncated",
                total_rejected=total,
                logged=REJECTION_LOG_SAMPLE_LIMIT,
            )

    def record_run_metric(self, *, success: bool) -> None:
        meter = self._meter or get_meter()
        counter = meter.register_counter(
            MetricDescriptor(
                logical_name="collector_runs_total",
                metric_type="counter",
                description="Total collector runs",
                allowed_label_keys=frozenset({"status"}),
            )
        )
        counter.add(1.0, labels={"status": "success" if success else "failure"})

    def record_fetch_duration(self, *, seconds: float, success: bool) -> None:
        meter = self._meter or get_meter()
        histogram = meter.register_histogram(
            MetricDescriptor(
                logical_name="collector_fetch_duration_seconds",
                metric_type="histogram",
                description="Collector fetch phase duration",
                allowed_label_keys=frozenset({"status"}),
                unit="s",
            )
        )
        histogram.record(seconds, labels={"status": "success" if success else "failure"})

    def record_stories_fetched(self, *, count: int) -> None:
        meter = self._meter or get_meter()
        histogram = meter.register_histogram(
            MetricDescriptor(
                logical_name="collector_stories_fetched",
                metric_type="histogram",
                description="Stories fetched per collection run",
                allowed_label_keys=frozenset(),
            )
        )
        histogram.record(float(count))
