"""Shared contract-test fixtures for agents module (AGT-014, LLD §12)."""

from __future__ import annotations

import pytest

from config.types import AgentId

from .helpers import (
    build_agent_run_context,
    create_capturing_fake_provider,
    critic_input,
    minimal_agents_config,
    scenario_generation_input,
    topic_selection_input,
)


@pytest.fixture
def agents_config() -> object:
    return minimal_agents_config()


@pytest.fixture
def topic_input() -> object:
    return topic_selection_input()


@pytest.fixture
def scenario_input() -> object:
    return scenario_generation_input()


@pytest.fixture
def critic_input_fixture() -> object:
    return critic_input()


@pytest.fixture
def agent_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_API_KEY", "fake-test-key")


@pytest.fixture
def topic_agent_context(agent_env_keys: None, agents_config: object) -> tuple[object, object]:
    config = agents_config
    provider = create_capturing_fake_provider(config)
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    return context, provider
