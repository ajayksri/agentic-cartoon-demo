"""Pre-code test mold for COL-008 — CollectionResultBuilder (LLD §2.2, §4.12)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from collector import StorySource


_STARTED_AT = datetime(2026, 8, 31, 11, 0, 0, tzinfo=UTC)
_COLLECTED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _story_draft(source_id: str = "1") -> object:
    from collector.service import StoryDraft

    return StoryDraft(
        source=StorySource.HACKERNEWS,
        source_id=source_id,
        collected_at=_COLLECTED_AT,
        raw_observation={"id": source_id, "nested": {"value": 1}},
        title="Title",
        url="https://example.com",
        author="author",
        score=10,
        comment_count=2,
        published_at=_COLLECTED_AT,
        rank_score=1.5,
    )


def test_deep_freeze_mapping_prevents_mutation() -> None:
    """COL-TC-004: raw_observation deep-frozen; mutation attempt fails."""
    from collector.result import deep_freeze_mapping

    frozen = deep_freeze_mapping({"nested": {"value": 1}})

    with pytest.raises((TypeError, AttributeError)):
        frozen["nested"] = {"value": 2}  # type: ignore[index]


def test_deep_freeze_story_produces_frozen_record() -> None:
    """StoryDraft converts to immutable StoryRecord."""
    from collector.result import deep_freeze_story
    from collector.types import StoryRecord

    record = deep_freeze_story(_story_draft())

    assert isinstance(record, StoryRecord)
    assert record.source_id == "1"


def test_collection_result_mutation_raises_frozen_instance_error() -> None:
    """COL-TC-016: CollectionResult and nested records reject mutation."""
    from collector.result import CollectionResultBuilder
    from collector.service import CollectionRunContext

    context = CollectionRunContext(started_at=_STARTED_AT)
    draft = _story_draft()
    builder = CollectionResultBuilder()

    result = builder.build(
        context=context,
        ranked_stories=[draft],
        candidates=[draft],
        rejected=[],
    )

    with pytest.raises(FrozenInstanceError):
        result.stats = result.stats  # type: ignore[misc]


def test_build_stats_consistent_with_list_lengths() -> None:
    """COL-TC-017: stats counters match final collection list lengths."""
    from collector.result import CollectionResultBuilder
    from collector.service import CollectionRunContext

    context = CollectionRunContext(
        started_at=_STARTED_AT,
        fetched_count=3,
        duplicate_count=1,
    )
    drafts = [_story_draft("1"), _story_draft("2")]
    builder = CollectionResultBuilder()

    result = builder.build(
        context=context,
        ranked_stories=drafts,
        candidates=drafts[:1],
        rejected=[],
    )

    assert result.stats.accepted_count == len(result.stories)
    assert result.stats.rejected_count == len(result.rejected)
    assert result.stats.candidate_count == len(result.candidates)


def test_build_sets_completed_at_timezone_aware() -> None:
    """completed_at is timezone-aware UTC at build time."""
    from collector.result import CollectionResultBuilder
    from collector.service import CollectionRunContext

    context = CollectionRunContext(started_at=_STARTED_AT)
    draft = _story_draft()
    builder = CollectionResultBuilder()

    result = builder.build(
        context=context,
        ranked_stories=[draft],
        candidates=[draft],
        rejected=[],
    )

    assert result.completed_at.tzinfo is not None
    assert result.started_at == _STARTED_AT


def test_deep_freeze_rejected_prevents_raw_observation_mutation() -> None:
    """RejectedStoryRecord raw_observation is deep-frozen after build."""
    from collector import RejectionReason
    from collector.result import CollectionResultBuilder, deep_freeze_rejected
    from collector.service import CollectionRunContext
    from collector.types import RejectedStoryRecord

    rejected = RejectedStoryRecord(
        source=StorySource.HACKERNEWS,
        source_id="99",
        collected_at=_COLLECTED_AT,
        raw_observation={"id": "99", "nested": {"value": 1}},
        reason_code=RejectionReason.VALIDATION_FAILED,
        reason_detail="validation failed",
    )
    frozen = deep_freeze_rejected(rejected)

    with pytest.raises((TypeError, AttributeError)):
        frozen.raw_observation["nested"] = {"value": 2}  # type: ignore[index]

    context = CollectionRunContext(started_at=_STARTED_AT)
    builder = CollectionResultBuilder()
    result = builder.build(
        context=context,
        ranked_stories=[],
        candidates=[],
        rejected=[rejected],
    )

    with pytest.raises((TypeError, AttributeError)):
        result.rejected[0].raw_observation["mutated"] = True  # type: ignore[index]
