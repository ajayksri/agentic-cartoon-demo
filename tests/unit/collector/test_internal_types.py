"""Smoke tests for COL-001 — internal intermediate types (LLD §2)."""

from __future__ import annotations

from datetime import UTC, datetime

from collector.hn_client import FeedFetchResult, ItemFetchResult
from collector.hn_parser import RawObservation
from collector.ranker import ScoringWeights
from collector.service import CollectionRunContext, StoryDraft
from collector.types import StorySource


def test_collection_run_context_defaults() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    context = CollectionRunContext(started_at=started)

    assert context.started_at == started
    assert context.fetched_count == 0
    assert context.duplicate_count == 0
    assert context.rejected_records == []
    assert context.accepted_drafts == []


def test_story_draft_field_access() -> None:
    collected = datetime(2026, 1, 1, tzinfo=UTC)
    observation: RawObservation = {"id": 1, "title": "Example"}
    draft = StoryDraft(
        source=StorySource.HACKERNEWS,
        source_id="1",
        collected_at=collected,
        raw_observation=observation,
        title="Example",
        url="https://example.com",
        author="alice",
        score=42,
        comment_count=3,
        published_at=collected,
        rank_score=1.5,
    )

    assert draft.source is StorySource.HACKERNEWS
    assert draft.source_id == "1"
    assert draft.rank_score == 1.5


def test_scoring_weights_frozen() -> None:
    weights = ScoringWeights(
        weight_score=1.0,
        weight_comments=0.5,
        weight_recency=0.3,
    )
    assert weights.weight_score == 1.0
    assert weights.weight_comments == 0.5
    assert weights.weight_recency == 0.3


def test_fetch_result_types() -> None:
    feed = FeedFetchResult(story_ids=[1, 2, 3])
    item = ItemFetchResult(
        source_id="1",
        status_code=200,
        body=b'{"id": 1}',
        error_kind="none",
    )

    assert feed.story_ids == [1, 2, 3]
    assert item.source_id == "1"
    assert item.status_code == 200
    assert item.body == b'{"id": 1}'
    assert item.error_kind == "none"
