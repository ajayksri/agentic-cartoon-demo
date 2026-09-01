"""Pre-code test mold for COL-006 — StoryDeduplicator (LLD §4.10)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collector import RejectionReason, StorySource


_COLLECTED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _story_draft(source_id: str, title: str = "Story") -> object:
    from collector.service import StoryDraft

    return StoryDraft(
        source=StorySource.HACKERNEWS,
        source_id=source_id,
        collected_at=_COLLECTED_AT,
        raw_observation={"id": source_id, "title": title},
        title=title,
        url=None,
        author=None,
        score=None,
        comment_count=None,
        published_at=None,
    )


def test_dedupe_first_wins_preserves_feed_order() -> None:
    """COL-TC-008: first occurrence wins; feed order preserved in accepted list."""
    from collector.dedupe import StoryDeduplicator

    drafts = [_story_draft("1", "First"), _story_draft("2"), _story_draft("1", "Duplicate")]
    deduplicator = StoryDeduplicator()

    accepted, rejected = deduplicator.dedupe(drafts)

    assert [story.source_id for story in accepted] == ["1", "2"]
    assert len(rejected) == 1


def test_dedupe_duplicate_rejection_reason_and_fields() -> None:
    """Duplicate loser becomes DUPLICATE rejection with propagated fields."""
    from collector.dedupe import StoryDeduplicator
    from collector.types import RejectedStoryRecord

    drafts = [_story_draft("42", "Winner"), _story_draft("42", "Loser")]
    deduplicator = StoryDeduplicator()

    _, rejected = deduplicator.dedupe(drafts)
    loser = rejected[0]

    assert isinstance(loser, RejectedStoryRecord)
    assert loser.reason_code == RejectionReason.DUPLICATE
    assert loser.source_id == "42"
    assert loser.source == StorySource.HACKERNEWS
    assert loser.collected_at == _COLLECTED_AT
    assert loser.raw_observation["title"] == "Loser"


def test_dedupe_no_duplicates_passthrough() -> None:
    """Unique source_ids pass through unchanged."""
    from collector.dedupe import StoryDeduplicator

    drafts = [_story_draft("10"), _story_draft("11"), _story_draft("12")]
    deduplicator = StoryDeduplicator()

    accepted, rejected = deduplicator.dedupe(drafts)

    assert len(accepted) == 3
    assert rejected == []


def test_dedupe_triple_duplicate_emits_two_rejections() -> None:
    """Three entries with same source_id yield one accepted and two DUPLICATE rejections."""
    from collector.dedupe import StoryDeduplicator

    drafts = [_story_draft("7"), _story_draft("7"), _story_draft("7")]
    deduplicator = StoryDeduplicator()

    accepted, rejected = deduplicator.dedupe(drafts)

    assert len(accepted) == 1
    assert len(rejected) == 2
