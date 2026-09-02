"""Shared contract-test helpers for config module (CFG-011, LLD §10.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from config import ConfigSource


def _minimal_valid_config_dict() -> dict[str, Any]:
    """Base YAML dict covering all required domains per LLD §6–§7."""
    return {
        "config_version": "1",
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
                "prompt_file": "prompts/topic_selector/v1.txt",
            },
            "scenario_generator": {
                "provider": "openai",
                "model": "gpt-4",
                "prompt_file": "prompts/scenario_generator/v1.txt",
            },
            "critic": {
                "provider": "anthropic",
                "model": "claude-3",
                "prompt_file": "prompts/critic/v1.txt",
            },
        },
        "providers": {
            "openai": {"api_key_env": "OPENAI_API_KEY"},
            "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
            "fake": {"api_key_env": "FAKE_API_KEY"},
        },
        "collection": {"candidate_count": 10},
        "workflow": {"max_scenario_revisions": 2},
        "workers": {
            "topic_selector_concurrency": 2,
            "scenario_generator_concurrency": 3,
            "critic_concurrency": 1,
        },
        "retry": {
            "COLLECT": {
                "max_attempts": 3,
                "backoff": {
                    "initial_seconds": 1.0,
                    "multiplier": 2.0,
                    "max_seconds": 30.0,
                },
            },
            "SELECT_TOPIC": {
                "max_attempts": 3,
                "backoff": {
                    "initial_seconds": 1.0,
                    "multiplier": 2.0,
                    "max_seconds": 30.0,
                },
            },
            "GENERATE_SCENARIO": {
                "max_attempts": 3,
                "backoff": {
                    "initial_seconds": 1.0,
                    "multiplier": 2.0,
                    "max_seconds": 30.0,
                },
            },
            "REVIEW_SCENARIO": {
                "max_attempts": 3,
                "backoff": {
                    "initial_seconds": 1.0,
                    "multiplier": 2.0,
                    "max_seconds": 30.0,
                },
            },
        },
        "timeouts": {
            "openai": {"read_seconds": 60.0},
            "anthropic": {"read_seconds": 60.0},
            "gemini": {"read_seconds": 60.0},
        },
        "failure_injection": {
            "enabled": False,
            "active_injections": [],
        },
    }


def minimal_valid_config() -> dict[str, Any]:
    """Return a fresh minimal valid config dict."""
    return _minimal_valid_config_dict()


def write_config(tmp_path: Path, content: dict[str, Any] | str) -> ConfigSource:
    """Write temp config file and return ConfigSource pointing at it."""
    config_path = tmp_path / "cartoon.yaml"
    if isinstance(content, str):
        config_path.write_text(content, encoding="utf-8")
    else:
        config_path.write_text(
            yaml.safe_dump(content, sort_keys=False),
            encoding="utf-8",
        )
    return ConfigSource(path=config_path)


def seed_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set all env vars required by minimal_valid_config."""
    for name, value in {
        "OPENAI_API_KEY": "openai-test-key",
        "ANTHROPIC_API_KEY": "anthropic-test-key",
        "GEMINI_API_KEY": "gemini-test-key",
        "FAKE_API_KEY": "fake-test-key",
        "POSTGRES_USER": "postgres-user",
        "POSTGRES_PASSWORD": "postgres-password",
    }.items():
        monkeypatch.setenv(name, value)
