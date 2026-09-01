"""Pre-provider structured input validation."""

# GUARDRAIL: Input — reject malformed or out-of-policy agent inputs before any LLM call.

from __future__ import annotations

from config.types import AgentId

from agents.constants import MAX_TOPIC_CANDIDATES
from agents.errors import AgentInputValidationError
from agents.messages import input_validation_message
from agents.types import (
    CriticInput,
    ScenarioGenerationInput,
    TopicSelectionInput,
    TopicSelectionOutcome,
)


class InputValidator:
    """Validates agent inputs before provider invocation."""

    def validate_topic_selection(self, input: TopicSelectionInput) -> None:
        agent_id = AgentId.TOPIC_SELECTOR
        if len(input.candidates) == 0:
            raise AgentInputValidationError(
                input_validation_message(agent_id=agent_id, reason="empty candidates"),
                agent_id=agent_id,
            )
        if len(input.candidates) > MAX_TOPIC_CANDIDATES:
            raise AgentInputValidationError(
                input_validation_message(
                    agent_id=agent_id,
                    reason=f"candidate count exceeds {MAX_TOPIC_CANDIDATES}",
                ),
                agent_id=agent_id,
            )

    def validate_scenario_generation(self, input: ScenarioGenerationInput) -> None:
        agent_id = AgentId.SCENARIO_GENERATOR
        if input.topic.outcome != TopicSelectionOutcome.TOPIC_SELECTED:
            raise AgentInputValidationError(
                input_validation_message(
                    agent_id=agent_id,
                    reason="topic outcome is not topic_selected",
                ),
                agent_id=agent_id,
            )

    def validate_critic(self, input: CriticInput) -> None:
        agent_id = AgentId.CRITIC
        if len(input.scenario.panels) == 0:
            raise AgentInputValidationError(
                input_validation_message(agent_id=agent_id, reason="empty panels"),
                agent_id=agent_id,
            )
        if input.scenario.punchline.strip() == "":
            raise AgentInputValidationError(
                input_validation_message(agent_id=agent_id, reason="blank punchline"),
                agent_id=agent_id,
            )
