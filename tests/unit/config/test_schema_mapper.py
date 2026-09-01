"""Unit tests for CFG-006 — SchemaMapper (S2)."""

from __future__ import annotations

import copy

import pytest

from config.draft import ConfigDraft
from config.errors import ConfigFormatError, ConfigMissingError
from config.schema import SchemaMapper
from config.types import AgentId, ProviderId, TaskType


def _retry_policy() -> dict[str, object]:
    return {
        "max_attempts": 3,
        "backoff": {
            "initial_seconds": 1.0,
            "multiplier": 2.0,
            "max_seconds": 60.0,
        },
    }


def minimal_valid_raw_tree() -> dict[str, object]:
    """Local inline minimal valid raw dict per LLD §6–§7 (not contract conftest)."""
    return {
        "infrastructure": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "cartoon",
                "user_env": "POSTGRES_USER",
                "password_env": "POSTGRES_PASSWORD",
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0,
            },
        },
        "agents": {
            "topic_selector": {
                "provider": "gemini",
                "model": "gemini-pro",
                "prompt_file": "prompts/topic.txt",
            },
            "scenario_generator": {
                "provider": "openai",
                "model": "gpt-4",
                "prompt_file": "prompts/scenario.txt",
            },
            "critic": {
                "provider": "anthropic",
                "model": "claude-3",
                "prompt_file": "prompts/critic.txt",
            },
        },
        "providers": {
            "openai": {"api_key_env": "OPENAI_API_KEY"},
            "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
        "collection": {"candidate_count": 10},
        "workflow": {"max_scenario_revisions": 2},
        "workers": {
            "topic_selector_concurrency": 1,
            "scenario_generator_concurrency": 1,
            "critic_concurrency": 1,
        },
        "retry": {
            "COLLECT": _retry_policy(),
            "SELECT_TOPIC": _retry_policy(),
            "GENERATE_SCENARIO": _retry_policy(),
            "REVIEW_SCENARIO": _retry_policy(),
        },
        "timeouts": {
            "openai": {"read_seconds": 30.0},
            "anthropic": {"read_seconds": 30.0},
            "gemini": {"read_seconds": 30.0},
        },
    }


def test_minimal_valid_raw_tree_maps_to_config_draft() -> None:
    """Minimal valid inline raw dict maps to fully populated ConfigDraft."""
    mapper = SchemaMapper()
    draft = mapper.map(minimal_valid_raw_tree())

    assert isinstance(draft, ConfigDraft)
    assert len(draft.agents) == 3
    assert AgentId.TOPIC_SELECTOR in draft.agents
    assert len(draft.retry) == 4
    assert TaskType.COLLECT in draft.retry
    assert ProviderId.OPENAI in draft.timeouts


def test_defaults_applied_for_omitted_optional_domains() -> None:
    """Defaults: failure_injection, pricing, scoring, redis password_env, optional timeouts."""
    tree = minimal_valid_raw_tree()
    mapper = SchemaMapper()
    draft = mapper.map(tree)

    assert draft.failure_injection.enabled is False
    assert draft.failure_injection.active_injections == []
    assert draft.infrastructure.redis.password_env is None
    assert draft.collection.scoring is None
    assert draft.providers[ProviderId.OPENAI].pricing is None
    assert draft.providers[ProviderId.OPENAI].rate_limit_per_minute is None
    assert draft.timeouts[ProviderId.OPENAI].connect_seconds is None
    assert draft.timeouts[ProviderId.OPENAI].total_seconds is None


def test_missing_agent_raises_config_missing_error() -> None:
    """All three AgentId keys required — missing agent → ConfigMissingError."""
    tree = minimal_valid_raw_tree()
    agents = dict(tree["agents"])  # type: ignore[arg-type]
    del agents["critic"]
    tree["agents"] = agents

    mapper = SchemaMapper()

    with pytest.raises(ConfigMissingError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_MISSING"
    assert "critic" in exc_info.value.key_path


def test_missing_retry_task_type_raises_config_missing_error() -> None:
    """All four TaskType keys required under retry."""
    tree = minimal_valid_raw_tree()
    retry = dict(tree["retry"])  # type: ignore[arg-type]
    del retry["REVIEW_SCENARIO"]
    tree["retry"] = retry

    mapper = SchemaMapper()

    with pytest.raises(ConfigMissingError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_MISSING"
    assert "REVIEW_SCENARIO" in exc_info.value.key_path


def test_missing_timeout_for_referenced_provider_raises_config_missing_error() -> None:
    """timeouts entry required for each ProviderId referenced by any agent."""
    tree = minimal_valid_raw_tree()
    timeouts = dict(tree["timeouts"])  # type: ignore[arg-type]
    del timeouts["openai"]
    tree["timeouts"] = timeouts

    mapper = SchemaMapper()

    with pytest.raises(ConfigMissingError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_MISSING"
    assert "openai" in exc_info.value.key_path


def test_partial_collection_scoring_raises_config_missing_error() -> None:
    """CG-CFG-HLD-002: partial collection.scoring → ConfigMissingError for missing weight."""
    tree = minimal_valid_raw_tree()
    tree["collection"] = {
        "candidate_count": 10,
        "scoring": {"weight_score": 0.5, "weight_comments": 0.3},
    }

    mapper = SchemaMapper()

    with pytest.raises(ConfigMissingError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_MISSING"
    assert "weight_recency" in exc_info.value.key_path


def test_unknown_agent_key_raises_config_format_error() -> None:
    """LLD-CFG-002: unknown keys under agents → ConfigFormatError."""
    tree = minimal_valid_raw_tree()
    agents = dict(tree["agents"])  # type: ignore[arg-type]
    agents["unknown_agent"] = {
        "provider": "openai",
        "model": "gpt-4",
        "prompt_file": "prompts/x.txt",
    }
    tree["agents"] = agents

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "unknown" in exc_info.value.key_path


def test_unknown_provider_key_raises_config_format_error() -> None:
    """LLD-CFG-002: unknown keys under providers → ConfigFormatError."""
    tree = minimal_valid_raw_tree()
    providers = dict(tree["providers"])  # type: ignore[arg-type]
    providers["unknown_provider"] = {"api_key_env": "UNKNOWN_API_KEY"}
    tree["providers"] = providers

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "unknown" in exc_info.value.key_path


def test_unknown_retry_task_type_key_raises_config_format_error() -> None:
    """LLD-CFG-002: unknown keys under retry → ConfigFormatError."""
    tree = minimal_valid_raw_tree()
    retry = dict(tree["retry"])  # type: ignore[arg-type]
    retry["UNKNOWN_TASK"] = _retry_policy()
    tree["retry"] = retry

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "unknown" in exc_info.value.key_path.lower()


def test_unknown_timeout_provider_key_raises_config_format_error() -> None:
    """LLD-CFG-002: unknown keys under timeouts → ConfigFormatError."""
    tree = minimal_valid_raw_tree()
    timeouts = dict(tree["timeouts"])  # type: ignore[arg-type]
    timeouts["unknown_provider"] = {"read_seconds": 30.0}
    tree["timeouts"] = timeouts

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "unknown" in exc_info.value.key_path


def test_invalid_provider_enum_raises_config_format_error() -> None:
    """Invalid provider string under agents.*.provider → ConfigFormatError at map time."""
    tree = minimal_valid_raw_tree()
    agents = dict(tree["agents"])  # type: ignore[arg-type]
    topic_selector = dict(agents["topic_selector"])  # type: ignore[arg-type]
    topic_selector["provider"] = "unknown_provider"
    agents["topic_selector"] = topic_selector
    tree["agents"] = agents

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "provider" in exc_info.value.key_path


def test_empty_string_raises_config_format_error() -> None:
    """S2 _require_str: empty/whitespace-only strings → ConfigFormatError."""
    tree = minimal_valid_raw_tree()
    infra = copy.deepcopy(tree["infrastructure"])  # type: ignore[arg-type]
    postgres = dict(infra["postgres"])  # type: ignore[arg-type]
    postgres["host"] = "   "
    infra["postgres"] = postgres
    tree["infrastructure"] = infra

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert "host" in exc_info.value.key_path


def test_unsupported_config_version_raises_config_format_error() -> None:
    """Unsupported config_version → ConfigFormatError at key_path=config_version."""
    tree = minimal_valid_raw_tree()
    tree["config_version"] = "99"

    mapper = SchemaMapper()

    with pytest.raises(ConfigFormatError) as exc_info:
        mapper.map(tree)

    assert exc_info.value.code == "CFG_FORMAT"
    assert exc_info.value.key_path == "config_version"


def test_supported_config_version_accepted() -> None:
    """config_version '1' is accepted per SchemaMapper.SUPPORTED_CONFIG_VERSIONS."""
    tree = minimal_valid_raw_tree()
    tree["config_version"] = "1"

    mapper = SchemaMapper()
    draft = mapper.map(tree)

    assert draft.config_version == "1"
