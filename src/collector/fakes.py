"""Test doubles for collector unit and contract suites (LLD §4.1, §10.1)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from observability.fakes import create_fake_bindings
from observability.protocols import Span
from observability.settings import _ObservabilityConfig

from collector.errors import CollectorError
from collector.hn_client import FeedFetchResult, ItemFetchResult
from collector.observability import CollectionTelemetry
from collector.types import CollectionStats, RejectionReason


class StubHackerNewsClient:
    """Injectable HackerNewsClient for deterministic tests without live network."""

    def __init__(
        self,
        *,
        feed_ids: Sequence[int] | Exception = (),
        items: Mapping[int, object | Exception] | None = None,
    ) -> None:
        self._feed_ids = feed_ids
        self._items = items or {}

    def fetch_top_story_ids(self) -> FeedFetchResult:
        if isinstance(self._feed_ids, Exception):
            raise self._feed_ids
        return FeedFetchResult(story_ids=list(self._feed_ids))

    def fetch_items(self, story_ids: Sequence[int]) -> list[ItemFetchResult]:
        results: list[ItemFetchResult] = []
        for story_id in story_ids:
            payload = self._items.get(story_id)
            if isinstance(payload, Exception):
                raise payload
            if payload is None:
                results.append(
                    ItemFetchResult(
                        source_id=str(story_id),
                        status_code=404,
                        body=None,
                        error_kind="http",
                    )
                )
                continue

            body = json.dumps(payload).encode("utf-8")
            results.append(
                ItemFetchResult(
                    source_id=str(story_id),
                    status_code=200,
                    body=body,
                    error_kind="none",
                )
            )
        return results


class RecordingTelemetry(CollectionTelemetry):
    """Test double capturing collection telemetry for COL-TC-015 and unit tests."""

    def __init__(self) -> None:
        config = _ObservabilityConfig(
            service_name="collector-test",
            log_level="DEBUG",
            strict_telemetry_errors=True,
        )
        logger, meter, tracer, _correlation = create_fake_bindings(config)
        super().__init__(logger=logger, tracer=tracer, meter=meter)
        self.started_events: list[dict[str, object]] = []
        self.completed_events: list[dict[str, object]] = []
        self.fetch_failed_events: list[dict[str, object]] = []
        self.rejected_events: list[dict[str, object]] = []
        self.metrics: list[tuple[str, dict[str, object]]] = []
        self.root_spans: list[Span] = []

    def emit_started(self, *, candidate_count: int) -> Span:
        span = super().emit_started(candidate_count=candidate_count)
        self.started_events.append({"candidate_count": candidate_count})
        self.root_spans.append(span)
        return span

    def emit_completed(
        self,
        *,
        stats: CollectionStats,
        root_span: Span,
        story_count: int,
    ) -> None:
        super().emit_completed(stats=stats, root_span=root_span, story_count=story_count)
        self.completed_events.append(
            {
                "fetched_count": stats.fetched_count,
                "accepted_count": stats.accepted_count,
                "rejected_count": stats.rejected_count,
                "duplicate_count": stats.duplicate_count,
                "candidate_count": stats.candidate_count,
                "story_count": story_count,
            }
        )

    def emit_fetch_failed(self, *, error: CollectorError) -> None:
        super().emit_fetch_failed(error=error)
        self.fetch_failed_events.append(
            {
                "error_class": error.__class__.__name__,
                "code": error.code,
                "retryable": error.retryable,
            }
        )

    def emit_story_rejected(self, *, source_id: str, reason_code: RejectionReason) -> None:
        super().emit_story_rejected(source_id=source_id, reason_code=reason_code)
        self.rejected_events.append(
            {"source_id": source_id, "reason_code": str(reason_code)}
        )

    def record_run_metric(self, *, success: bool) -> None:
        super().record_run_metric(success=success)
        self.metrics.append(("collector_runs_total", {"status": "success" if success else "failure"}))

    def record_fetch_duration(self, *, seconds: float, success: bool) -> None:
        super().record_fetch_duration(seconds=seconds, success=success)
        self.metrics.append(
            (
                "collector_fetch_duration_seconds",
                {"seconds": seconds, "status": "success" if success else "failure"},
            )
        )

    def record_stories_fetched(self, *, count: int) -> None:
        super().record_stories_fetched(count=count)
        self.metrics.append(("collector_stories_fetched", {"count": count}))
