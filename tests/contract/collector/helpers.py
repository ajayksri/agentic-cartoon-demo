"""Shared contract-test helpers for collector module (COL-012, LLD §10.3)."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from collector import CollectionResult
from config import (
    AgentConfig,
    AgentId,
    AppConfig,
    BackoffConfig,
    CollectionConfig,
    CollectionScoringConfig,
    FailureInjectionConfig,
    InfrastructureConfig,
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

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "collector"


def fixtures_dir() -> Path:
    return _FIXTURES


def load_collector_fixture(name: str) -> Any:
    """Load JSON fixture bytes from tests/fixtures/collector/."""
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def minimal_collection_config(
    *,
    candidate_count: int = 10,
    scoring: CollectionScoringConfig | None = None,
) -> AppConfig:
    """Valid AppConfig with configurable collection domain."""
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
        collection=CollectionConfig(candidate_count=candidate_count, scoring=scoring),
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


def hn_story_item(**fields: object) -> dict[str, object]:
    """Build HN item JSON dict for stub client injection."""
    base: dict[str, object] = {
        "type": "story",
        "title": "Fixture Story",
        "by": "fixture_author",
        "score": 10,
        "descendants": 1,
        "time": 1704067200,
    }
    base.update(fields)
    if "id" in base:
        base["id"] = int(base["id"])  # type: ignore[call-overload]
    return base


def hn_feed(*ids: int) -> list[int]:
    """Top stories ID list for stub feed."""
    return list(ids)


def collect_with_stub(config: AppConfig, stub: object) -> CollectionResult:
    """Injection seam per LLD §10.1 — boundary import allowed here only."""
    from collector.service import DefaultCollector

    collector = DefaultCollector(hn_client=stub)
    return collector.collect_stories(config=config)


def make_stub(
    *,
    feed_ids: list[int] | Exception,
    items: Mapping[int, object | Exception] | None = None,
) -> object:
    """Build StubHackerNewsClient without importing fakes in contract test modules."""
    from collector.fakes import StubHackerNewsClient

    return StubHackerNewsClient(feed_ids=feed_ids, items=items)


@contextmanager
def recording_observability() -> Iterator[None]:
    """Reset observability and wire in-memory fakes for COL-TC-015."""
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="collector-contract",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    try:
        yield
    finally:
        _reset_observability_state()


def story_items_from_fixture(name: str) -> dict[int, dict[str, object]]:
    """Load a single story fixture keyed by its HN id."""
    payload = load_collector_fixture(name)
    story_id = int(payload["id"])
    return {story_id: payload}


def large_story_batch(count: int = 22) -> tuple[list[int], Mapping[int, dict[str, object]]]:
    """Generate feed IDs and item payloads for COL-TC-010."""
    feed_ids = list(range(8001, 8001 + count))
    items = {
        story_id: hn_story_item(
            id=story_id,
            title=f"Story {story_id}",
            score=story_id % 100,
            descendants=story_id % 20,
            time=1704067200 + story_id,
        )
        for story_id in feed_ids
    }
    return feed_ids, items
