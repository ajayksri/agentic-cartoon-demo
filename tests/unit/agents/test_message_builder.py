"""Pre-code test mold for AGT-007 — MessageBuilder (LLD §4.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import (
    AgentPromptLoadError,
    CandidateStory,
    CriticInput,
    EvaluationScores,
    ScenarioGenerationInput,
    ScenarioOutput,
    ScenarioPanel,
    TopicSelectionInput,
    TopicSelectionOutcome,
    TopicSelectionOutput,
)
from config.types import AgentId


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPTS = _REPO_ROOT / "prompts"


def _topic_input() -> TopicSelectionInput:
    return TopicSelectionInput(
        candidates=(
            CandidateStory(
                source_id="src-1",
                title="Rust async",
                url="https://example.com/1",
                score=100,
                comment_count=42,
                rank_score=0.95,
            ),
            CandidateStory(source_id="src-2", title="Go generics"),
            CandidateStory(source_id="src-3", title="Python typing"),
        ),
    )


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


def test_topic_messages_contain_candidate_fields_only() -> None:
    """AGT-TC-001: candidate JSON excludes workflow metadata."""
    from agents.prompts.builder import MessageBuilder
    from providers import ProviderMessageRole

    prompt_text = (_PROMPTS / "topic_selector" / "v1.txt").read_text(encoding="utf-8")
    messages = MessageBuilder().build_topic_messages(
        prompt_text=prompt_text,
        input=_topic_input(),
        agent_id=AgentId.TOPIC_SELECTOR,
    )

    assert len(messages) == 2
    system, user = messages
    assert system.role == ProviderMessageRole.SYSTEM
    assert user.role == ProviderMessageRole.USER

    for message in messages:
        if message.role != ProviderMessageRole.USER:
            continue
        if "{{" in message.content:
            continue
        payload = json.loads(message.content)
        assert isinstance(payload, list)
        for item in payload:
            assert set(item.keys()) <= {
                "source_id",
                "title",
                "url",
                "score",
                "comment_count",
                "rank_score",
            }
            assert "workflow_id" not in item
            assert "task_id" not in item

    user_payload = json.loads(user.content)
    assert len(user_payload) == 3


def test_topic_user_message_matches_candidate_json() -> None:
    """AGT-TC-001: stage payload duplicated in USER message."""
    from agents.prompts.builder import MessageBuilder
    from providers import ProviderMessageRole

    prompt_text = (_PROMPTS / "topic_selector" / "v1.txt").read_text(encoding="utf-8")
    messages = MessageBuilder().build_topic_messages(
        prompt_text=prompt_text,
        input=_topic_input(),
        agent_id=AgentId.TOPIC_SELECTOR,
    )
    user = next(message for message in messages if message.role == ProviderMessageRole.USER)
    candidates_json = json.dumps(
        [
            {
                "source_id": "src-1",
                "title": "Rust async",
                "url": "https://example.com/1",
                "score": 100,
                "comment_count": 42,
                "rank_score": 0.95,
            },
            {"source_id": "src-2", "title": "Go generics"},
            {"source_id": "src-3", "title": "Python typing"},
        ],
        separators=(",", ":"),
    )
    assert candidates_json in user.content or json.loads(user.content) == json.loads(candidates_json)


def test_scenario_messages_substitute_template_variables() -> None:
    from agents.prompts.builder import MessageBuilder

    prompt_text = (_PROMPTS / "scenario_generator" / "v1.txt").read_text(encoding="utf-8")
    messages = MessageBuilder().build_scenario_messages(
        prompt_text=prompt_text,
        input=ScenarioGenerationInput(topic=_topic_selected_output()),
        agent_id=AgentId.SCENARIO_GENERATOR,
    )
    system_text = messages[0].content
    assert "Rust async" in system_text
    assert "Hot debate" in system_text
    assert "Crabs with shells" in system_text
    assert "{{" not in system_text


def test_critic_messages_include_revision_number() -> None:
    """CG-AGT-010: revision_number is prompt context only."""
    from agents.prompts.builder import MessageBuilder

    prompt_text = (_PROMPTS / "critic" / "v1.txt").read_text(encoding="utf-8")
    messages = MessageBuilder().build_critic_messages(
        prompt_text=prompt_text,
        input=CriticInput(scenario=_scenario_output(), revision_number=7),
        agent_id=AgentId.CRITIC,
    )
    assert "7" in messages[0].content
    assert "{{revision_number}}" not in messages[0].content


def test_unresolved_template_variables_raise_prompt_load_error() -> None:
    from agents.prompts.builder import MessageBuilder

    with pytest.raises(AgentPromptLoadError, match="unresolved template variables"):
        MessageBuilder().build_topic_messages(
            prompt_text="Hello {{unknown_var}}",
            input=_topic_input(),
            agent_id=AgentId.TOPIC_SELECTOR,
        )


def test_lld_prompt_fixtures_exist() -> None:
    for agent in ("topic_selector", "scenario_generator", "critic"):
        assert (_PROMPTS / agent / "v1.txt").is_file()
