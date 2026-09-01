"""Scenario generation agent implementation."""

from __future__ import annotations

from agents.base import BaseAgent
from agents.protocols import ScenarioGenerationAgent
from agents.types import AgentRunContext, ScenarioGenerationInput, ScenarioOutput


class ScenarioGenerationAgentImpl(BaseAgent, ScenarioGenerationAgent):
    """Convert selected topic into a validated scenario."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: ScenarioGenerationInput,
    ) -> ScenarioOutput:
        result = self._run_pipeline(
            context=context,
            input=input,
            build_user_payload=lambda _: "{}",
            validate_input=self._input_validator.validate_scenario_generation,
            parse_and_validate_output=lambda content, version: self._schema_validator.validate_scenario_output(
                self._schema_validator.parse_provider_content(
                    content,
                    agent_id=context.agent_id,
                ),
                prompt_version=version,
            ),
            emit_stage_outcome=None,
        )
        assert isinstance(result, ScenarioOutput)
        return result
