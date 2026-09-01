"""Critic agent implementation."""

# GUARDRAIL: Quality — second agent reviews scenario output; PASS/REVISE before human escalation.

from __future__ import annotations

from agents.base import BaseAgent
from agents.protocols import CriticAgent
from agents.types import AgentRunContext, CriticInput, CriticOutput


class CriticAgentImpl(BaseAgent, CriticAgent):
    """Review scenario and return validated critic verdict."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: CriticInput,
    ) -> CriticOutput:
        def _emit_stage_outcome(_ctx: AgentRunContext, output: object) -> None:
            from agents.types import CriticOutput as CriticResult

            assert isinstance(output, CriticResult)
            assert self._current_telemetry is not None
            self._current_telemetry.record_stage_outcome_critic(status=output.status)
            self._current_telemetry.log_critic_verdict(status=output.status)

        result = self._run_pipeline(
            context=context,
            input=input,
            build_user_payload=lambda _: "{}",
            validate_input=self._input_validator.validate_critic,
            parse_and_validate_output=lambda content, version: self._schema_validator.validate_critic_output(
                self._schema_validator.parse_provider_content(
                    content,
                    agent_id=context.agent_id,
                ),
                prompt_version=version,
            ),
            emit_stage_outcome=_emit_stage_outcome,
        )
        assert isinstance(result, CriticOutput)
        return result
