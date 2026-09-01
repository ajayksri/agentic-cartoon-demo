"""Story ranking and scoring weight resolution."""

# GUARDRAIL: Input — deterministic candidate reduction caps how many stories agents evaluate.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from config.types import CollectionScoringConfig

from collector.service import StoryDraft


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    weight_score: float
    weight_comments: float
    weight_recency: float


class ScoringWeightsResolver:
    def resolve(self, scoring: CollectionScoringConfig | None) -> ScoringWeights:
        if scoring is None:
            return ScoringWeights(
                weight_score=1.0,
                weight_comments=0.5,
                weight_recency=0.3,
            )

        return ScoringWeights(
            weight_score=scoring.weight_score if scoring.weight_score is not None else 0.0,
            weight_comments=(
                scoring.weight_comments if scoring.weight_comments is not None else 0.0
            ),
            weight_recency=(
                scoring.weight_recency if scoring.weight_recency is not None else 0.0
            ),
        )


class StoryRanker:
    def __init__(self, *, weights_resolver: ScoringWeightsResolver | None = None) -> None:
        self._weights_resolver = weights_resolver or ScoringWeightsResolver()

    def rank(
        self,
        stories: Sequence[StoryDraft],
        *,
        candidate_count: int,
        weights: ScoringWeights,
    ) -> tuple[list[StoryDraft], list[StoryDraft]]:
        ref_published_at = self._reference_published_at(stories)

        scored: list[tuple[StoryDraft, float]] = []
        for story in stories:
            rank_score = self._compute_rank_score(story, weights, ref_published_at)
            scored.append((replace(story, rank_score=rank_score), rank_score))

        ranked = [
            story
            for story, _ in sorted(
                scored,
                key=lambda item: (-item[1], item[0].source_id),
            )
        ]
        return ranked, ranked[:candidate_count]

    def _reference_published_at(self, stories: Sequence[StoryDraft]):
        published_times = [
            story.published_at for story in stories if story.published_at is not None
        ]
        if not published_times:
            return None
        return max(published_times)

    def _compute_rank_score(
        self,
        story: StoryDraft,
        weights: ScoringWeights,
        ref_published_at,
    ) -> float:
        score_sig = float(story.score) if story.score is not None else 0.0
        comment_sig = float(story.comment_count) if story.comment_count is not None else 0.0
        recency_sig = self._recency_signal(story.published_at, ref_published_at)
        return (
            weights.weight_score * score_sig
            + weights.weight_comments * comment_sig
            + weights.weight_recency * recency_sig
        )

    def _recency_signal(self, published_at, ref_published_at) -> float:
        if published_at is None or ref_published_at is None:
            return 0.0

        age_hours = max(
            0.0,
            (ref_published_at - published_at).total_seconds() / 3600.0,
        )
        return 1.0 / (1.0 + age_hours)
