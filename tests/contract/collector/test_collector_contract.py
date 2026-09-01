"""Contract tests COL-TC-001 through COL-TC-018 (COL-012).

Imports ONLY from the collector package public surface (`collector.__init__`).
Boundary imports for stub injection live in conftest.py per LLD §10.1.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from collector import (
    CollectorFetchError,
    CollectorResponseError,
    CollectionResult,
    RejectionReason,
    StorySource,
)
from .helpers import (
    collect_with_stub,
    hn_feed,
    hn_story_item,
    large_story_batch,
    load_collector_fixture,
    make_stub,
    minimal_collection_config,
    recording_observability,
    story_items_from_fixture,
)
from config import CollectionScoringConfig

@pytest.mark.col_tc("001")
def test_col_tc_001_transient_fetch_failure_is_retryable() -> None:
    """COL-TC-001: retryable fetch failure raises CollectorFetchError COL_FETCH."""
    stub = make_stub(feed_ids=CollectorFetchError("HN unreachable"))
    config = minimal_collection_config(candidate_count=2)

    with pytest.raises(CollectorFetchError) as exc_info:
        collect_with_stub(config, stub)

    assert exc_info.value.code == "COL_FETCH"
    assert exc_info.value.retryable is True


@pytest.mark.col_tc("002")
def test_col_tc_002_malformed_top_level_response_is_permanent() -> None:
    """COL-TC-002: invalid feed payload raises CollectorResponseError COL_RESPONSE."""
    stub = make_stub(feed_ids=CollectorResponseError("feed not parseable"))
    config = minimal_collection_config(candidate_count=2)

    with pytest.raises(CollectorResponseError) as exc_info:
        collect_with_stub(config, stub)

    assert exc_info.value.code == "COL_RESPONSE"
    assert exc_info.value.retryable is False


@pytest.mark.col_tc("003")
def test_col_tc_003_required_fields_populated_from_fixture() -> None:
    """COL-TC-003: accepted StoryRecord has source, source_id, collected_at, normalized fields."""
    story = load_collector_fixture("complete_story.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=2)

    result = collect_with_stub(config, stub)

    assert len(result.stories) >= 1
    record = result.stories[0]
    assert record.source == StorySource.HACKERNEWS
    assert record.source_id == str(story_id)
    assert record.collected_at.tzinfo is not None
    assert record.title == "Complete Story Title"


@pytest.mark.col_tc("004")
def test_col_tc_004_raw_observation_retained_and_immutable() -> None:
    """COL-TC-004: raw_observation non-empty and not mutable by caller."""
    story = load_collector_fixture("complete_story.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=1)

    result = collect_with_stub(config, stub)
    record = result.stories[0]

    assert record.raw_observation
    with pytest.raises((TypeError, AttributeError, FrozenInstanceError)):
        record.raw_observation["mutated"] = True  # type: ignore[index]


@pytest.mark.col_tc("005")
def test_col_tc_005_whitespace_normalization_on_title() -> None:
    """COL-TC-005: title whitespace collapsed per normalization algorithm."""
    story = load_collector_fixture("story_whitespace_title.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=1)

    result = collect_with_stub(config, stub)

    assert result.stories[0].title == "Hello World"


@pytest.mark.col_tc("006")
def test_col_tc_006_url_normalization_is_deterministic() -> None:
    """COL-TC-006: URL pairs 1, 2, 6 canonicalize identically across runs."""
    vectors = load_collector_fixture("url_vectors.json")["pairs"]
    selected = [v for v in vectors if v["id"] in {1, 2, 6}]
    config = minimal_collection_config(candidate_count=3)

    canonical_urls: list[str] = []
    for vector in selected:
        story_id = 9000 + int(vector["id"])
        story = hn_story_item(id=story_id, title=f"URL {vector['id']}", url=str(vector["input"]))
        stub = make_stub(feed_ids=[story_id], items={story_id: story})
        result_a = collect_with_stub(config, stub)
        result_b = collect_with_stub(config, stub)
        url = result_a.stories[0].url
        assert url == result_b.stories[0].url
        canonical_urls.append(url or "")

    assert canonical_urls[0] == "https://example.com/Path"
    assert canonical_urls[1] == "https://example.com/page"
    assert canonical_urls[2] == "https://ex.com/?a=1&b=2"


@pytest.mark.col_tc("007")
def test_col_tc_007_invalid_required_fields_rejected() -> None:
    """COL-TC-007: missing title appears in rejected, not stories/candidates."""
    story = load_collector_fixture("story_missing_title.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=2)

    result = collect_with_stub(config, stub)

    assert result.stories == ()
    assert result.candidates == ()
    assert any(r.reason_code == RejectionReason.VALIDATION_FAILED for r in result.rejected)


@pytest.mark.col_tc("008")
def test_col_tc_008_duplicate_removal_within_batch() -> None:
    """COL-TC-008: duplicate source_id yields one story; duplicate_count incremented."""
    story = load_collector_fixture("complete_story.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id, story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=5)

    result = collect_with_stub(config, stub)

    assert len(result.stories) == 1
    assert result.stats.duplicate_count == 1


@pytest.mark.col_tc("009")
def test_col_tc_009_optional_missing_fields_stored_as_null() -> None:
    """COL-TC-009: omitted score stored as None."""
    story = load_collector_fixture("story_no_score.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=1)

    result = collect_with_stub(config, stub)

    assert result.stories[0].score is None


@pytest.mark.col_tc("010")
def test_col_tc_010_candidate_count_respected() -> None:
    """COL-TC-010: candidate_count cap honored when >=20 stories available."""
    feed_ids, items = large_story_batch(count=22)
    stub = make_stub(feed_ids=feed_ids, items=items)
    config = minimal_collection_config(candidate_count=5)

    result = collect_with_stub(config, stub)

    assert len(result.candidates) == 5
    assert result.stats.candidate_count == 5


@pytest.mark.col_tc("011")
def test_col_tc_011_fewer_candidates_when_insufficient_stories() -> None:
    """COL-TC-011: fewer accepted stories than candidate_count returns all accepted."""
    items = story_items_from_fixture("complete_story.json")
    items.update(story_items_from_fixture("story_no_score.json"))
    items.update(story_items_from_fixture("story_whitespace_title.json"))
    feed_ids = hn_feed(*items.keys())
    stub = make_stub(feed_ids=feed_ids, items=items)
    config = minimal_collection_config(candidate_count=10)

    result = collect_with_stub(config, stub)

    assert len(result.candidates) == 3


@pytest.mark.col_tc("012")
def test_col_tc_012_scoring_configuration_changes_ranking() -> None:
    """COL-TC-012: different scoring weights change candidate ordering."""
    high_score = hn_story_item(id=9101, title="High Score", score=200, descendants=1, time=1704067200)
    high_comments = hn_story_item(
        id=9102,
        title="High Comments",
        score=1,
        descendants=500,
        time=1704067100,
    )
    items = {9101: high_score, 9102: high_comments}
    stub = make_stub(feed_ids=hn_feed(9101, 9102), items=items)

    config_score = minimal_collection_config(
        candidate_count=2,
        scoring=CollectionScoringConfig(weight_score=1.0, weight_comments=0.0, weight_recency=0.0),
    )
    config_comments = minimal_collection_config(
        candidate_count=2,
        scoring=CollectionScoringConfig(weight_score=0.0, weight_comments=1.0, weight_recency=0.0),
    )

    result_score = collect_with_stub(config_score, stub)
    result_comments = collect_with_stub(config_comments, stub)

    assert result_score.candidates[0].source_id != result_comments.candidates[0].source_id


@pytest.mark.col_tc("013")
def test_col_tc_013_deterministic_ranking_for_identical_input() -> None:
    """COL-TC-013: identical fixture and config produce identical ranking."""
    feed_ids, items = large_story_batch(count=10)
    stub = make_stub(feed_ids=feed_ids, items=items)
    config = minimal_collection_config(candidate_count=5)

    result_a = collect_with_stub(config, stub)
    result_b = collect_with_stub(config, stub)

    ids_a = [story.source_id for story in result_a.candidates]
    ids_b = [story.source_id for story in result_b.candidates]
    scores_a = [story.rank_score for story in result_a.candidates]
    scores_b = [story.rank_score for story in result_b.candidates]

    assert ids_a == ids_b
    assert scores_a == scores_b


@pytest.mark.col_tc("014")
def test_col_tc_014_no_code_execution_from_source_content() -> None:
    """COL-TC-014: script-like strings stored as inert text only."""
    story = load_collector_fixture("story_script_like.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=1)

    result = collect_with_stub(config, stub)

    assert "<script>" in (result.stories[0].title or "")
    assert "javascript:" in (result.stories[0].url or "")


@pytest.mark.col_tc("015")
def test_col_tc_015_error_logs_omit_raw_payloads() -> None:
    """COL-TC-015: fetch failure logs do not contain full raw HN body."""
    from observability import get_logger
    from observability.fakes import InMemoryLogger

    raw_body = "X" * 8000 + '{"secret_body": true}'
    stub = make_stub(feed_ids=CollectorFetchError(f"failed with body prefix {raw_body[:100]}"))

    with recording_observability():
        config = minimal_collection_config(candidate_count=1)
        with pytest.raises(CollectorFetchError):
            collect_with_stub(config, stub)

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert raw_body not in joined
        assert '"secret_body": true' not in joined


@pytest.mark.col_tc("016")
def test_col_tc_016_result_immutability() -> None:
    """COL-TC-016: mutating CollectionResult raises FrozenInstanceError."""
    story = load_collector_fixture("complete_story.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=1)

    result = collect_with_stub(config, stub)

    with pytest.raises(FrozenInstanceError):
        result.completed_at = result.completed_at  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.stories[0].title = "mutated"  # type: ignore[misc]

    with pytest.raises((TypeError, AttributeError, FrozenInstanceError)):
        result.stories[0].raw_observation["mutated"] = True  # type: ignore[index]


@pytest.mark.col_tc("017")
def test_col_tc_017_stats_consistency() -> None:
    """COL-TC-017: stats counters match collection list lengths."""
    feed_ids, items = large_story_batch(count=8)
    stub = make_stub(feed_ids=feed_ids, items=items)
    config = minimal_collection_config(candidate_count=4)

    result = collect_with_stub(config, stub)

    assert result.stats.accepted_count == len(result.stories)
    assert result.stats.rejected_count == len(result.rejected)
    assert result.stats.candidate_count == len(result.candidates)


@pytest.mark.col_tc("018")
def test_col_tc_018_all_stories_rejected() -> None:
    """COL-TC-018: all-invalid fixture yields empty success, not exception."""
    story = load_collector_fixture("story_missing_title.json")
    story_id = int(story["id"])
    stub = make_stub(feed_ids=[story_id], items={story_id: story})
    config = minimal_collection_config(candidate_count=5)

    result = collect_with_stub(config, stub)

    assert isinstance(result, CollectionResult)
    assert result.stories == ()
    assert result.candidates == ()
