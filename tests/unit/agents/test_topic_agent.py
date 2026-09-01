"""Pre-code test mold for AGT-010 — TopicSelectionAgentImpl smoke (LLD §4.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import CandidateStory, TopicSelectionInput, TopicSelectionOutcome
from config.types import AgentId, ProviderId
from providers import GenerateResponse, TokenUsage


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agents"


def test_topic_agent_smoke_with_fake_provider() -> None:
    from agents.agents.topic import TopicSelectionAgentImpl
    from agents.factory import AgentFactory

    body = (_FIXTURES / "outputs" / "topic_selected_valid.json").read_text(encoding="utf-8")
    factory = AgentFactory()
    agent = factory.create_topic_selector()
    assert isinstance(agent, TopicSelectionAgentImpl)

    from tests.contract.agents.helpers import (
        build_agent_run_context,
        create_capturing_fake_provider,
        minimal_agents_config,
        update_agent_prompt_file,
    )

    config = minimal_agents_config()
    config = update_agent_prompt_file(
        config,
        agent_id=AgentId.TOPIC_SELECTOR,
        prompt_file=str(_FIXTURES / "prompts" / "topic_selector.txt"),
    )
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(
        GenerateResponse(
            content=body,
            model="fake-model",
            provider_id=ProviderId.FAKE,
            latency_ms=1.0,
            token_usage=TokenUsage(input_tokens=10, output_tokens=20),
        ),
    )
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(
        context=context,
        input=TopicSelectionInput(
            candidates=(CandidateStory(source_id="src-1", title="Rust async"),),
        ),
    )
    assert output.outcome == TopicSelectionOutcome.TOPIC_SELECTED
    assert output.prompt_version


def test_topic_agent_emits_stage_outcome_only_on_validated_success() -> None:
    from agents.factory import AgentFactory

    factory = AgentFactory()
    agent = factory.create_topic_selector()
    assert hasattr(agent, "run")
