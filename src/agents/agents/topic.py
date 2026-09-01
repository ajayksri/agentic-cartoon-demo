"""Topic selection agent implementation."""

from __future__ import annotations

from agents.base import BaseAgent
from agents.protocols import TopicSelectionAgent
from agents.types import AgentRunContext, TopicSelectionInput, TopicSelectionOutput


class TopicSelectionAgentImpl(BaseAgent, TopicSelectionAgent):
    """Evaluate candidates and return validated topic selection output."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: TopicSelectionInput,
    ) -> TopicSelectionOutput:
        def _emit_stage_outcome(_ctx: AgentRunContext, output: object) -> None:
            from agents.types import TopicSelectionOutput as TopicOutput

            assert isinstance(output, TopicOutput)
            assert self._current_telemetry is not None
            self._current_telemetry.record_stage_outcome_topic(outcome=output.outcome)

        result = self._run_pipeline(
            context=context,
            input=input,
            build_user_payload=lambda _: "[]",
            validate_input=self._input_validator.validate_topic_selection,
            parse_and_validate_output=lambda content, version: self._schema_validator.validate_topic_output(
                self._schema_validator.parse_provider_content(
                    content,
                    agent_id=context.agent_id,
                ),
                prompt_version=version,
            ),
            emit_stage_outcome=_emit_stage_outcome,
        )
        assert isinstance(result, TopicSelectionOutput)
        return result
