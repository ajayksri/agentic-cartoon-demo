"""Pre-code test mold for COL-007 — StoryRanker (LLD §4.11, §8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config import CollectionScoringConfig


_BASE_TIME = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _story_draft(
    source_id: str,
    *,
    score: int | None = 10,
    comment_count: int | None = 5,
    published_at: datetime | None = None,
) -> object:
    from collector import StorySource
    from collector.service import StoryDraft

    return StoryDraft(
        source=StorySource.HACKERNEWS,
        source_id=source_id,
        collected_at=_BASE_TIME,
        raw_observation={"id": source_id},
        title=f"Story {source_id}",
        url=None,
        author=None,
        score=score,
        comment_count=comment_count,
        published_at=published_at or _BASE_TIME,
    )


def test_weights_resolver_defaults_when_scoring_none() -> None:
    """Default weights match LLD when scoring config is None."""
    from collector.ranker import ScoringWeightsResolver

    resolver = ScoringWeightsResolver()
    weights = resolver.resolve(None)

    assert weights.weight_score == 1.0
    assert weights.weight_comments == 0.5
    assert weights.weight_recency == 0.3


def test_ranker_respects_candidate_count_cap() -> None:
    """COL-TC-010: candidate slice length equals candidate_count cap."""
    from collector.ranker import ScoringWeightsResolver, StoryRanker

    stories = [_story_draft(str(i), score=i) for i in range(20)]
    ranker = StoryRanker()
    weights = ScoringWeightsResolver().resolve(None)

    all_ranked, candidates = ranker.rank(stories, candidate_count=5, weights=weights)

    assert len(all_ranked) == 20
    assert len(candidates) == 5


def test_ranker_fewer_candidates_when_insufficient_stories() -> None:
    """COL-TC-011: fewer than candidate_count stories returns all accepted."""
    from collector.ranker import ScoringWeightsResolver, StoryRanker

    stories = [_story_draft("1"), _story_draft("2"), _story_draft("3")]
    ranker = StoryRanker()
    weights = ScoringWeightsResolver().resolve(None)

    _, candidates = ranker.rank(stories, candidate_count=10, weights=weights)

    assert len(candidates) == 3


def test_ranker_scoring_config_changes_ordering() -> None:
    """COL-TC-012: different weight configs produce different candidate ordering."""
    from collector.ranker import ScoringWeightsResolver, StoryRanker

    stories = [
        _story_draft("high-score", score=100, comment_count=1, published_at=_BASE_TIME),
        _story_draft(
            "high-comments",
            score=1,
            comment_count=200,
            published_at=_BASE_TIME - timedelta(hours=1),
        ),
    ]
    ranker = StoryRanker()
    resolver = ScoringWeightsResolver()

    score_weights = resolver.resolve(
        CollectionScoringConfig(weight_score=1.0, weight_comments=0.0, weight_recency=0.0)
    )
    comment_weights = resolver.resolve(
        CollectionScoringConfig(weight_score=0.0, weight_comments=1.0, weight_recency=0.0)
    )

    _, score_first = ranker.rank(stories, candidate_count=2, weights=score_weights)
    _, comment_first = ranker.rank(stories, candidate_count=2, weights=comment_weights)

    assert score_first[0].source_id != comment_first[0].source_id


def test_ranker_deterministic_for_identical_input() -> None:
    """COL-TC-013: identical inputs yield identical rank_score and ordering."""
    from collector.ranker import ScoringWeightsResolver, StoryRanker

    stories = [_story_draft("b", score=20), _story_draft("a", score=20)]
    ranker = StoryRanker()
    weights = ScoringWeightsResolver().resolve(None)

    ranked_a, candidates_a = ranker.rank(stories, candidate_count=2, weights=weights)
    ranked_b, candidates_b = ranker.rank(stories, candidate_count=2, weights=weights)

    assert [s.source_id for s in candidates_a] == [s.source_id for s in candidates_b]
    assert [s.rank_score for s in ranked_a] == [s.rank_score for s in ranked_b]


def test_ranker_tie_break_by_ascending_source_id() -> None:
    """Stable sort tie-break uses ascending source_id string compare."""
    from collector.ranker import ScoringWeightsResolver, StoryRanker

    stories = [_story_draft("2", score=50), _story_draft("10", score=50)]
    ranker = StoryRanker()
    weights = ScoringWeightsResolver().resolve(None)

    _, candidates = ranker.rank(stories, candidate_count=2, weights=weights)

    assert [story.source_id for story in candidates] == ["10", "2"]


def test_ranker_recency_zero_when_no_published_at() -> None:
    """COL-TC-013: stories without published_at contribute zero recency signal."""
    from collector import StorySource
    from collector.ranker import ScoringWeightsResolver, StoryRanker
    from collector.service import StoryDraft

    stories = [
        StoryDraft(
            source=StorySource.HACKERNEWS,
            source_id="a",
            collected_at=_BASE_TIME,
            raw_observation={"id": "a"},
            title="Story a",
            url=None,
            author=None,
            score=10,
            comment_count=5,
            published_at=None,
        ),
        StoryDraft(
            source=StorySource.HACKERNEWS,
            source_id="b",
            collected_at=_BASE_TIME,
            raw_observation={"id": "b"},
            title="Story b",
            url=None,
            author=None,
            score=10,
            comment_count=5,
            published_at=None,
        ),
    ]
    ranker = StoryRanker()
    weights = ScoringWeightsResolver().resolve(
        CollectionScoringConfig(weight_score=0.0, weight_comments=0.0, weight_recency=1.0)
    )

    ranked, _ = ranker.rank(stories, candidate_count=2, weights=weights)

    assert all(story.rank_score == 0.0 for story in ranked)
