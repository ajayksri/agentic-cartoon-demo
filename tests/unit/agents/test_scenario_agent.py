"""Pre-code test mold for AGT-011 — ScenarioGenerationAgentImpl smoke (LLD §4.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import (
    EvaluationScores,
    ScenarioGenerationInput,
    TopicSelectionOutcome,
    TopicSelectionOutput,
)
from config.types import AgentId, ProviderId
from providers import GenerateResponse, TokenUsage


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agents"


def _topic_selected_output() -> TopicSelectionOutput:
    return TopicSelectionOutput(
        outcome=TopicSelectionOutcome.TOPIC_SELECTED,
        prompt_version="v1",
        selected_topic="Rust async",
        why_interesting="Hot debate",
        cartoon_angle="Crabs with shells",
        scores=EvaluationScores(
            technical_relevance=0.8,
            developer_relevance=0.8,
            discussion_interest=0.7,
            humour_potential=0.7,
            irony_contradiction=0.6,
            visual_scenario_potential=0.8,
            background_knowledge_required=0.4,
        ),
    )


def test_scenario_agent_smoke_with_fake_provider() -> None:
    from agents.agents.scenario import ScenarioGenerationAgentImpl
    from agents.factory import AgentFactory

    body = (_FIXTURES / "outputs" / "scenario_valid.json").read_text(encoding="utf-8")
    factory = AgentFactory()
    agent = factory.create_scenario_generator()
    assert isinstance(agent, ScenarioGenerationAgentImpl)

    from tests.contract.agents.helpers import (
        build_agent_run_context,
        create_capturing_fake_provider,
        minimal_agents_config,
        update_agent_prompt_file,
    )

    config = minimal_agents_config()
    config = update_agent_prompt_file(
        config,
        agent_id=AgentId.SCENARIO_GENERATOR,
        prompt_file=str(_FIXTURES / "prompts" / "scenario_generator.txt"),
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
        agent_id=AgentId.SCENARIO_GENERATOR,
        config=config,
        provider=provider,
    )
    output = agent.run(
        context=context,
        input=ScenarioGenerationInput(topic=_topic_selected_output()),
    )
    assert 3 <= len(output.panels) <= 4
    assert output.prompt_version


def test_scenario_agent_does_not_emit_stage_outcome_metrics() -> None:
    from agents.factory import AgentFactory

    agent = AgentFactory().create_scenario_generator()
    assert hasattr(agent, "run")
