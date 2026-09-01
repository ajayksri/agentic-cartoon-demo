"""Story deduplication by source identity."""

# GUARDRAIL: Input — reject duplicate stories so agents see a bounded, deduplicated set.

from __future__ import annotations

from collections.abc import Sequence

from collector.messages import rejection_detail
from collector.service import StoryDraft
from collector.types import RejectedStoryRecord, RejectionReason, StorySource


class StoryDeduplicator:
    def dedupe(
        self,
        accepted: Sequence[StoryDraft],
    ) -> tuple[list[StoryDraft], list[RejectedStoryRecord]]:
        seen: set[tuple[StorySource, str]] = set()
        kept: list[StoryDraft] = []
        rejected: list[RejectedStoryRecord] = []

        for draft in accepted:
            key = (draft.source, draft.source_id)
            if key in seen:
                rejected.append(
                    RejectedStoryRecord(
                        source=draft.source,
                        source_id=draft.source_id,
                        collected_at=draft.collected_at,
                        raw_observation=draft.raw_observation,
                        reason_code=RejectionReason.DUPLICATE,
                        reason_detail=rejection_detail(reason_code=RejectionReason.DUPLICATE),
                    )
                )
                continue

            seen.add(key)
            kept.append(draft)

        return kept, rejected
