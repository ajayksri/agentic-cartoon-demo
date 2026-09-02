"""Pre-code test mold for AGT-012 — CriticAgentImpl smoke (LLD §4.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import CriticInput, CriticStatus, ScenarioOutput, ScenarioPanel
from config.types import AgentId, ProviderId
from providers import GenerateResponse, TokenUsage


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agents"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPTS = _REPO_ROOT / "prompts"


def _scenario_output() -> ScenarioOutput:
    return ScenarioOutput(
        topic="Rust async",
        premise="Developers argue",
        characters=("Alice", "Bob"),
        panels=(
            ScenarioPanel(scene="Office", dialogue="Async!"),
            ScenarioPanel(scene="Office", dialogue="Await!"),
            ScenarioPanel(scene="Office", dialogue="Ship it!"),
        ),
        punchline="Blocking I/O wins.",
        prompt_version="v1",
    )


def test_critic_agent_smoke_with_fake_provider() -> None:
    from agents.agents.critic import CriticAgentImpl
    from agents.factory import AgentFactory

    body = (_FIXTURES / "outputs" / "critic_revise_valid.json").read_text(encoding="utf-8")
    factory = AgentFactory()
    agent = factory.create_critic()
    assert isinstance(agent, CriticAgentImpl)

    from tests.contract.agents.helpers import (
        build_agent_run_context,
        create_capturing_fake_provider,
        minimal_agents_config,
        update_agent_prompt_file,
    )

    config = minimal_agents_config()
    config = update_agent_prompt_file(
        config,
        agent_id=AgentId.CRITIC,
        prompt_file=str(_PROMPTS / "critic" / "v1.txt"),
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
        agent_id=AgentId.CRITIC,
        config=config,
        provider=provider,
    )
    output = agent.run(
        context=context,
        input=CriticInput(scenario=_scenario_output(), revision_number=99),
    )
    assert output.status == CriticStatus.REVISE
    assert len(output.issues) == 3
    assert output.prompt_version


def test_critic_agent_accepts_high_revision_number() -> None:
    """AGT-TC-034: revision limit not enforced by critic agent."""
    from agents.factory import AgentFactory

    agent = AgentFactory().create_critic()
    assert hasattr(agent, "run")
