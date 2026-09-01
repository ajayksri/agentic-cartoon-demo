"""Collection result assembly and deep-freeze helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType

from collector.service import CollectionRunContext, StoryDraft
from collector.types import (
    CollectionResult,
    CollectionStats,
    RejectedStoryRecord,
    StoryRecord,
)


def deep_freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen_children: dict[str, object] = {}
    for key, child in value.items():
        if isinstance(child, dict):
            frozen_children[key] = deep_freeze_mapping(child)
        elif isinstance(child, list):
            frozen_children[key] = tuple(
                deep_freeze_mapping(item) if isinstance(item, dict) else item for item in child
            )
        else:
            frozen_children[key] = child
    return MappingProxyType(frozen_children)


def deep_freeze_story(draft: StoryDraft) -> StoryRecord:
    return StoryRecord(
        source=draft.source,
        source_id=draft.source_id,
        collected_at=draft.collected_at,
        raw_observation=deep_freeze_mapping(draft.raw_observation),
        title=draft.title,
        url=draft.url,
        author=draft.author,
        score=draft.score,
        comment_count=draft.comment_count,
        published_at=draft.published_at,
        rank_score=draft.rank_score,
    )


def deep_freeze_rejected(draft: RejectedStoryRecord) -> RejectedStoryRecord:
    return RejectedStoryRecord(
        source=draft.source,
        source_id=draft.source_id,
        collected_at=draft.collected_at,
        raw_observation=deep_freeze_mapping(dict(draft.raw_observation)),
        reason_code=draft.reason_code,
        reason_detail=draft.reason_detail,
    )


class CollectionResultBuilder:
    def build(
        self,
        *,
        context: CollectionRunContext,
        ranked_stories: Sequence[StoryDraft],
        candidates: Sequence[StoryDraft],
        rejected: Sequence[RejectedStoryRecord],
    ) -> CollectionResult:
        completed_at = datetime.now(UTC)
        frozen_stories = tuple(deep_freeze_story(story) for story in ranked_stories)
        frozen_candidates = tuple(deep_freeze_story(story) for story in candidates)
        frozen_rejected = tuple(deep_freeze_rejected(record) for record in rejected)

        stats = CollectionStats(
            fetched_count=context.fetched_count,
            accepted_count=len(frozen_stories),
            rejected_count=len(frozen_rejected),
            duplicate_count=context.duplicate_count,
            candidate_count=len(frozen_candidates),
        )

        if stats.accepted_count != len(frozen_stories):
            raise ValueError("accepted_count must equal len(stories)")
        if stats.rejected_count != len(frozen_rejected):
            raise ValueError("rejected_count must equal len(rejected)")
        if stats.candidate_count != len(frozen_candidates):
            raise ValueError("candidate_count must equal len(candidates)")

        return CollectionResult(
            started_at=context.started_at,
            completed_at=completed_at,
            stories=frozen_stories,
            candidates=frozen_candidates,
            rejected=frozen_rejected,
            stats=stats,
        )
