"""Pre-code test mold for AGT-003 — InputValidator (LLD §4.3)."""

from __future__ import annotations

import pytest

from agents import (
    AgentInputValidationError,
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



def _topic_selected_output() -> TopicSelectionOutput:
    return TopicSelectionOutput(
        outcome=TopicSelectionOutcome.TOPIC_SELECTED,
        prompt_version="abc123",
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
        prompt_version="def456",
    )


def test_empty_candidates_raises_input_validation_error() -> None:
    """AGT-TC-013: empty candidates rejected before provider."""
    from agents.validation.input import InputValidator

    validator = InputValidator()
    with pytest.raises(AgentInputValidationError) as exc_info:
        validator.validate_topic_selection(TopicSelectionInput(candidates=()))

    assert exc_info.value.code == "AGT_INPUT"
    assert "AGT_INPUT:" in str(exc_info.value)


def test_too_many_candidates_raises_input_validation_error() -> None:
    from agents.constants import MAX_TOPIC_CANDIDATES
    from agents.validation.input import InputValidator

    candidates = tuple(
        CandidateStory(source_id=f"src-{index}", title=f"Story {index}")
        for index in range(MAX_TOPIC_CANDIDATES + 1)
    )
    validator = InputValidator()
    with pytest.raises(AgentInputValidationError):
        validator.validate_topic_selection(TopicSelectionInput(candidates=candidates))


def test_no_suitable_topic_rejected_for_scenario_agent() -> None:
    """AGT-TC-021: scenario input requires TOPIC_SELECTED outcome."""
    from agents.validation.input import InputValidator

    topic = TopicSelectionOutput(
        outcome=TopicSelectionOutcome.NO_SUITABLE_TOPIC,
        prompt_version="abc123",
    )
    validator = InputValidator()
    with pytest.raises(AgentInputValidationError):
        validator.validate_scenario_generation(ScenarioGenerationInput(topic=topic))


def test_critic_rejects_empty_panels() -> None:
    from agents.validation.input import InputValidator

    scenario = ScenarioOutput(
        topic="Rust",
        premise="Debate",
        characters=("Alice",),
        panels=(),
        punchline="Done.",
        prompt_version="v1",
    )
    validator = InputValidator()
    with pytest.raises(AgentInputValidationError):
        validator.validate_critic(CriticInput(scenario=scenario, revision_number=1))


def test_critic_rejects_blank_punchline() -> None:
    from agents.validation.input import InputValidator

    scenario = ScenarioOutput(
        topic="Rust",
        premise="Debate",
        characters=("Alice",),
        panels=(ScenarioPanel(scene="Office", dialogue="Hi"),),
        punchline="   ",
        prompt_version="v1",
    )
    validator = InputValidator()
    with pytest.raises(AgentInputValidationError):
        validator.validate_critic(CriticInput(scenario=scenario, revision_number=1))


def test_critic_accepts_high_revision_number() -> None:
    """AGT-TC-034 seam: revision limit not enforced at input validation."""
    from agents.validation.input import InputValidator

    validator = InputValidator()
    validator.validate_critic(CriticInput(scenario=_scenario_output(), revision_number=999))


def test_error_messages_use_agt_input_shape() -> None:
    from agents.validation.input import InputValidator

    validator = InputValidator()
    with pytest.raises(AgentInputValidationError) as exc_info:
        validator.validate_topic_selection(TopicSelectionInput(candidates=()))
    assert exc_info.value.code == "AGT_INPUT"
    assert "AGT_INPUT:" in str(exc_info.value)
