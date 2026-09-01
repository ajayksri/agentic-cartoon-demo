"""Public type definitions for the collector module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class StorySource(StrEnum):
    """Known story origin identifiers."""

    HACKERNEWS = "hackernews"


class RejectionReason(StrEnum):
    """Reason a story was excluded during normalization or validation."""

    VALIDATION_FAILED = "validation_failed"
    DUPLICATE = "duplicate"
    NORMALIZATION_FAILED = "normalization_failed"
    UNTRUSTED_CONTENT = "untrusted_content"


@dataclass(frozen=True, slots=True)
class StoryRecord:
    """Normalized story with retained raw source observation."""

    source: StorySource
    source_id: str
    collected_at: datetime
    raw_observation: Mapping[str, object]
    title: str | None = None
    url: str | None = None
    author: str | None = None
    score: int | None = None
    comment_count: int | None = None
    published_at: datetime | None = None
    rank_score: float | None = None


@dataclass(frozen=True, slots=True)
class RejectedStoryRecord:
    """Story excluded during normalization or validation."""

    source: StorySource
    source_id: str
    collected_at: datetime
    raw_observation: Mapping[str, object]
    reason_code: RejectionReason
    reason_detail: str


@dataclass(frozen=True, slots=True)
class CollectionStats:
    """Summary counts for one collection run."""

    fetched_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    candidate_count: int


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Outcome of a single Hacker News collection run."""

    started_at: datetime
    completed_at: datetime
    stories: tuple[StoryRecord, ...]
    candidates: tuple[StoryRecord, ...]
    rejected: tuple[RejectedStoryRecord, ...]
    stats: CollectionStats
