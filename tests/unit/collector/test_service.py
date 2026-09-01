"""Pre-code test mold for COL-011 — DefaultCollector orchestration (LLD §9)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from config import CollectionConfig

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "collector"


def _minimal_config(candidate_count: int = 5) -> object:
    from config import (
        AgentConfig,
        AgentId,
        AppConfig,
        BackoffConfig,
        FailureInjectionConfig,
        InfrastructureConfig,
        InjectionId,
        PostgresConfig,
        ProviderConfig,
        ProviderId,
        RedisConfig,
        RetryPolicy,
        TaskType,
        TimeoutConfig,
        WorkerConfig,
        WorkflowConfig,
    )

    return AppConfig(
        infrastructure=InfrastructureConfig(
            postgres=PostgresConfig(
                host="localhost",
                port=5432,
                database="test",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisConfig(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentConfig(
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/topic_selector.txt",
            ),
        },
        providers={
            ProviderId.GEMINI: ProviderConfig(
                api_key_env="GEMINI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionConfig(candidate_count=candidate_count, scoring=None),
        workflow=WorkflowConfig(max_scenario_revisions=2),
        workers=WorkerConfig(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(
                    initial_seconds=1.0,
                    multiplier=2.0,
                    max_seconds=30.0,
                ),
            ),
        },
        timeouts={},
        failure_injection=FailureInjectionConfig(
            enabled=False,
            active_injections=frozenset(),
        ),
    )


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_collect_stories_pipeline_with_stub_client() -> None:
    """Full pipeline succeeds with injected StubHackerNewsClient."""
    from collector.fakes import StubHackerNewsClient
    from collector.service import DefaultCollector

    story = _load_fixture("complete_story.json")
    stub = StubHackerNewsClient(feed_ids=[1001], items={1001: story})
    collector = DefaultCollector(hn_client=stub)
    config = _minimal_config(candidate_count=1)

    result = collector.collect_stories(config=config)

    assert len(result.stories) >= 1
    assert result.stats.accepted_count == len(result.stories)


def test_collect_stories_fetch_failure_reraises_after_telemetry() -> None:
    """CollectorError path re-raises same exception after telemetry emit."""
    from collector.errors import CollectorFetchError
    from collector.fakes import StubHackerNewsClient
    from collector.service import DefaultCollector

    stub = StubHackerNewsClient(feed_ids=CollectorFetchError("feed down"))
    collector = DefaultCollector(hn_client=stub)

    with pytest.raises(CollectorFetchError):
        collector.collect_stories(config=_minimal_config())


def test_collect_stories_all_invalid_returns_empty_success() -> None:
    """COL-TC-018: all stories rejected yields empty stories/candidates, no exception."""
    from collector.fakes import StubHackerNewsClient
    from collector.service import DefaultCollector

    invalid = _load_fixture("story_missing_title.json")
    stub = StubHackerNewsClient(feed_ids=[3001], items={3001: invalid})
    collector = DefaultCollector(hn_client=stub)

    result = collector.collect_stories(config=_minimal_config(candidate_count=5))

    assert result.stories == ()
    assert result.candidates == ()
    assert result.stats.rejected_count >= 1


def test_collect_stories_duplicate_count_in_stats() -> None:
    """Duplicate merge increments duplicate_count and rejects loser (COL-TC-008)."""
    from collector.fakes import StubHackerNewsClient
    from collector.service import DefaultCollector

    story = _load_fixture("complete_story.json")
    duplicate = dict(story)
    duplicate["title"] = "Duplicate Title"
    stub = StubHackerNewsClient(feed_ids=[1001, 1001], items={1001: story})
    collector = DefaultCollector(hn_client=stub)

    result = collector.collect_stories(config=_minimal_config(candidate_count=2))

    assert result.stats.duplicate_count == 1
    assert len(result.stories) == 1


def test_collect_stories_collected_at_timezone_aware() -> None:
    """Accepted StoryRecord collected_at is timezone-aware per MOD-COL-INV-003."""
    from collector.fakes import StubHackerNewsClient
    from collector.service import DefaultCollector

    story = _load_fixture("complete_story.json")
    stub = StubHackerNewsClient(feed_ids=[1001], items={1001: story})
    collector = DefaultCollector(hn_client=stub)

    result = collector.collect_stories(config=_minimal_config(candidate_count=1))

    assert result.stories[0].collected_at.tzinfo is not None
    assert result.stories[0].collected_at >= datetime(2020, 1, 1, tzinfo=UTC)


def test_collect_stories_invalid_json_rejected_without_fetched_count() -> None:
    """reject_json fetch-phase path rejects item and does not increment fetched_count."""
    from collector import RejectionReason
    from collector.hn_client import FeedFetchResult, ItemFetchResult
    from collector.service import DefaultCollector

    class InvalidJsonStub:
        def fetch_top_story_ids(self) -> FeedFetchResult:
            return FeedFetchResult(story_ids=[5001])

        def fetch_items(self, story_ids: object) -> list[ItemFetchResult]:
            return [
                ItemFetchResult(
                    source_id=str(story_id),
                    status_code=200,
                    body=b"not-json",
                    error_kind="none",
                )
                for story_id in story_ids
            ]

    collector = DefaultCollector(hn_client=InvalidJsonStub())
    result = collector.collect_stories(config=_minimal_config(candidate_count=1))

    assert result.stories == ()
    assert result.stats.fetched_count == 0
    assert result.stats.rejected_count == 1
    assert result.rejected[0].reason_code == RejectionReason.NORMALIZATION_FAILED
