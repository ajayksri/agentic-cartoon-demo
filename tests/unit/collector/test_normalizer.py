"""Pre-code test mold for COL-005 — StoryNormalizer (LLD §4.9, §7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collector import RejectionReason, StorySource


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "collector"
_COLLECTED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_normalize_collapses_title_whitespace() -> None:
    """COL-TC-005: internal and edge whitespace collapsed in title."""
    from collector.normalizer import StoryNormalizer
    from collector.service import StoryDraft

    normalizer = StoryNormalizer()
    observation = _load_fixture("story_whitespace_title.json")

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, StoryDraft)
    assert result.title == "Hello World"


def test_normalize_missing_title_rejects_validation_failed() -> None:
    """COL-TC-007: missing required title yields VALIDATION_FAILED rejection."""
    from collector.normalizer import StoryNormalizer
    from collector.types import RejectedStoryRecord

    normalizer = StoryNormalizer()
    observation = _load_fixture("story_missing_title.json")

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, RejectedStoryRecord)
    assert result.reason_code == RejectionReason.VALIDATION_FAILED
    assert result.source == StorySource.HACKERNEWS


def test_normalize_optional_score_none_when_absent() -> None:
    """COL-TC-009: omitted score stored as None — not invented."""
    from collector.normalizer import StoryNormalizer
    from collector.service import StoryDraft

    normalizer = StoryNormalizer()
    observation = _load_fixture("story_no_score.json")

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, StoryDraft)
    assert result.score is None


def test_normalize_untrusted_content_rejection() -> None:
    """Control characters in fields trigger UNTRUSTED_CONTENT rejection."""
    from collector.normalizer import StoryNormalizer
    from collector.types import RejectedStoryRecord

    normalizer = StoryNormalizer()
    observation = _load_fixture("complete_story.json")
    observation = dict(observation)
    observation["title"] = "bad\x00title"

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, RejectedStoryRecord)
    assert result.reason_code == RejectionReason.UNTRUSTED_CONTENT


def test_normalize_published_at_from_unix_time() -> None:
    """HN unix time maps to timezone-aware UTC published_at."""
    from collector.normalizer import StoryNormalizer
    from collector.service import StoryDraft

    normalizer = StoryNormalizer()
    observation = _load_fixture("complete_story.json")

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, StoryDraft)
    assert result.published_at is not None
    assert result.published_at.tzinfo is not None


def test_normalize_unparseable_timestamp_rejects_validation_failed() -> None:
    """Unparseable HN time field yields VALIDATION_FAILED rejection."""
    from collector.normalizer import StoryNormalizer
    from collector.types import RejectedStoryRecord

    normalizer = StoryNormalizer()
    observation = _load_fixture("complete_story.json")
    observation = dict(observation)
    observation["time"] = "not-a-timestamp"

    result = normalizer.normalize(observation, collected_at=_COLLECTED_AT)

    assert isinstance(result, RejectedStoryRecord)
    assert result.reason_code == RejectionReason.VALIDATION_FAILED
