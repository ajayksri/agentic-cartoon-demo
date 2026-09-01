"""DefaultCollector orchestration and internal draft types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from collector.constants import compute_pool_size
from collector.errors import CollectorError
from collector.hn_parser import RawObservation
from collector.messages import rejection_detail
from collector.types import (
    CollectionResult,
    RejectedStoryRecord,
    RejectionReason,
    StorySource,
)

if TYPE_CHECKING:
    from config.types import AppConfig

    from collector.dedupe import StoryDeduplicator
    from collector.hn_client import HackerNewsClient
    from collector.hn_parser import HackerNewsParser
    from collector.normalizer import StoryNormalizer
    from collector.observability import CollectionTelemetry
    from collector.ranker import StoryRanker
    from collector.result import CollectionResultBuilder


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class CollectionRunContext:
    started_at: datetime
    fetched_count: int = 0
    duplicate_count: int = 0
    rejected_records: list[RejectedStoryRecord] = field(default_factory=list)
    accepted_drafts: list[StoryDraft] = field(default_factory=list)


@dataclass
class StoryDraft:
    """Mutable pre-ranking story; converted to frozen StoryRecord by result builder."""

    source: StorySource
    source_id: str
    collected_at: datetime
    raw_observation: dict[str, object]
    title: str
    url: str | None
    author: str | None
    score: int | None
    comment_count: int | None
    published_at: datetime | None
    rank_score: float | None = None


class RejectionRecordBuilder:
    """Orchestration-level RejectedStoryRecord factory (MOD-COL-INV-003)."""

    def build(
        self,
        *,
        source_id: str,
        reason_code: RejectionReason,
        collected_at: datetime,
        raw_observation: RawObservation | None = None,
        reason_detail: str | None = None,
        stage: str | None = None,
        field: str | None = None,
    ) -> RejectedStoryRecord:
        from collector.result import deep_freeze_mapping

        detail = reason_detail
        if detail is None:
            detail = rejection_detail(
                reason_code=reason_code,
                stage=stage,
                field=field,
            )
        else:
            detail = detail[:200]

        observation = raw_observation if raw_observation is not None else {}
        frozen_observation = deep_freeze_mapping(observation)

        return RejectedStoryRecord(
            source=StorySource.HACKERNEWS,
            source_id=source_id,
            collected_at=collected_at,
            raw_observation=frozen_observation,
            reason_code=reason_code,
            reason_detail=detail,
        )


class DefaultCollector:
    """Implements Collector protocol."""

    def __init__(
        self,
        *,
        hn_client: HackerNewsClient | None = None,
        parser: HackerNewsParser | None = None,
        normalizer: StoryNormalizer | None = None,
        deduplicator: StoryDeduplicator | None = None,
        ranker: StoryRanker | None = None,
        result_builder: CollectionResultBuilder | None = None,
        telemetry: CollectionTelemetry | None = None,
    ) -> None:
        from collector.dedupe import StoryDeduplicator
        from collector.hn_client import (
            DefaultHackerNewsClient,
            FetchErrorClassifier,
            ResponseDecoder,
        )
        from collector.hn_parser import HackerNewsParser
        from collector.normalizer import StoryNormalizer
        from collector.observability import CollectionTelemetry
        from collector.ranker import ScoringWeightsResolver, StoryRanker
        from collector.result import CollectionResultBuilder

        self._hn_client = hn_client or DefaultHackerNewsClient()
        self._parser = parser or HackerNewsParser()
        self._normalizer = normalizer or StoryNormalizer()
        self._deduplicator = deduplicator or StoryDeduplicator()
        self._ranker = ranker or StoryRanker()
        self._result_builder = result_builder or CollectionResultBuilder()
        self._telemetry = telemetry or CollectionTelemetry()
        self._decoder = ResponseDecoder()
        self._classifier = FetchErrorClassifier()
        self._rejection_builder = RejectionRecordBuilder()
        self._weights_resolver = ScoringWeightsResolver()

    def collect_stories(self, *, config: AppConfig) -> CollectionResult:
        from collector.hn_client import FetchErrorClassifier, ResponseDecoder
        from collector.ranker import ScoringWeightsResolver

        context = CollectionRunContext(started_at=utc_now())
        root_span = self._telemetry.emit_started(
            candidate_count=config.collection.candidate_count
        )

        try:
            pool_size = compute_pool_size(config.collection.candidate_count)

            root_span.add_event("fetch_started")
            feed_result = self._hn_client.fetch_top_story_ids()
            story_ids = feed_result.story_ids[:pool_size]
            root_span.add_event("fetch_completed")

            fetch_started = time.monotonic()
            item_results = self._hn_client.fetch_items(story_ids)
            queued: list[tuple[str, RawObservation]] = []

            for result in item_results:
                outcome = self._classifier.classify_item_failure(result)
                if outcome == "skip":
                    continue

                if outcome == "reject_json":
                    collected_at = utc_now()
                    context.rejected_records.append(
                        self._rejection_builder.build(
                            source_id=result.source_id,
                            reason_code=RejectionReason.NORMALIZATION_FAILED,
                            stage="json_decode",
                            collected_at=collected_at,
                        )
                    )
                    continue

                context.fetched_count += 1
                observation = self._decoder.decode_item(
                    result.body or b"",
                    source_id=result.source_id,
                )
                if observation is not None:
                    queued.append((result.source_id, observation))

            fetch_seconds = time.monotonic() - fetch_started
            self._telemetry.record_fetch_duration(seconds=fetch_seconds, success=True)
            self._telemetry.record_stories_fetched(count=context.fetched_count)

            for source_id, observation in queued:
                collected_at = utc_now()
                parsed, parse_outcome = self._parser.parse_item(observation)

                if parse_outcome == "skip":
                    continue

                if parse_outcome == "reject_deleted":
                    context.rejected_records.append(
                        self._rejection_builder.build(
                            source_id=source_id,
                            reason_code=RejectionReason.VALIDATION_FAILED,
                            stage="deleted_story",
                            collected_at=collected_at,
                            raw_observation=observation,
                        )
                    )
                    continue

                normalized = self._normalizer.normalize(
                    parsed,
                    collected_at=collected_at,
                )
                if isinstance(normalized, RejectedStoryRecord):
                    context.rejected_records.append(normalized)
                else:
                    context.accepted_drafts.append(normalized)

            deduped, duplicate_rejections = self._deduplicator.dedupe(context.accepted_drafts)
            context.rejected_records.extend(duplicate_rejections)
            context.duplicate_count += len(duplicate_rejections)

            weights = self._weights_resolver.resolve(config.collection.scoring)
            all_ranked, candidates = self._ranker.rank(
                deduped,
                candidate_count=config.collection.candidate_count,
                weights=weights,
            )
            root_span.add_event("rank_completed")

            self._telemetry.emit_rejections_sampled(context.rejected_records)
            result = self._result_builder.build(
                context=context,
                ranked_stories=all_ranked,
                candidates=candidates,
                rejected=context.rejected_records,
            )
            self._telemetry.emit_completed(
                stats=result.stats,
                root_span=root_span,
                story_count=len(result.stories),
            )
            self._telemetry.record_run_metric(success=True)
            return result
        except CollectorError as exc:
            self._telemetry.emit_fetch_failed(error=exc)
            self._telemetry.record_run_metric(success=False)
            raise


_DEFAULT_COLLECTOR: DefaultCollector | None = None


def collect_stories(*, config: AppConfig) -> CollectionResult:
    global _DEFAULT_COLLECTOR
    if _DEFAULT_COLLECTOR is None:
        _DEFAULT_COLLECTOR = DefaultCollector()
    return _DEFAULT_COLLECTOR.collect_stories(config=config)
