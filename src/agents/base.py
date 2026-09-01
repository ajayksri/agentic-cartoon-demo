"""Shared agent run orchestration."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Agent/execution separation — agents perform stateless
# LLM reasoning only; workers own idempotency, leases, persistence, and queue ACK.
# GUARDRAIL: Role separation — agents cannot ACK tasks, persist state, or apply transitions.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from config.types import AgentConfig, AgentId
from observability.protocols import Span
from providers.errors import ProviderError
from providers.types import GenerateRequest, ProviderMessage

from agents.constants import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_TEMPERATURE
from agents.errors import (
    AgentConfigurationError,
    AgentOutputValidationError,
    AgentPromptLoadError,
)
from agents.messages import configuration_error_message
from agents.prompts.builder import MessageBuilder
from agents.prompts.loader import PromptLoader
from agents.telemetry import AgentTelemetry
from agents.types import AgentRunContext, ValidationResult
from agents.validation.input import InputValidator
from agents.validation.schema import SchemaValidator


class AgentStage(StrEnum):
    TOPIC_SELECTION = "topic_selection"
    SCENARIO_GENERATION = "scenario_generation"
    CRITIC = "critic"


@dataclass
class RunCallContext:
    agent_id: AgentId
    agent_config: AgentConfig
    model: str
    prompt_version: str | None = None
    span: Span | None = None


class BaseAgent:
    """Shared run orchestration for all agent stages."""

    def __init__(
        self,
        *,
        stage: AgentStage,
        prompt_loader: PromptLoader,
        input_validator: InputValidator,
        message_builder: MessageBuilder,
        schema_validator: SchemaValidator,
        telemetry_factory: Callable[[AgentRunContext], AgentTelemetry],
    ) -> None:
        self._stage = stage
        self._prompt_loader = prompt_loader
        self._input_validator = input_validator
        self._message_builder = message_builder
        self._schema_validator = schema_validator
        self._telemetry_factory = telemetry_factory
        self._current_telemetry: AgentTelemetry | None = None

    def _resolve_agent_config(self, context: AgentRunContext) -> AgentConfig:
        try:
            agent_config = context.config.get_agent_config(context.agent_id)
        except KeyError as exc:
            raise AgentConfigurationError(
                configuration_error_message(
                    agent_id=context.agent_id,
                    reason="missing agent config",
                ),
                agent_id=context.agent_id,
            ) from exc

        if agent_config.model.strip() == "":
            raise AgentConfigurationError(
                configuration_error_message(
                    agent_id=context.agent_id,
                    reason="empty model",
                ),
                agent_id=context.agent_id,
            )

        if context.provider.provider_id != agent_config.provider:
            raise AgentConfigurationError(
                configuration_error_message(
                    agent_id=context.agent_id,
                    reason="provider mismatch",
                ),
                agent_id=context.agent_id,
            )

        return agent_config

    def _build_generate_request(
        self,
        context: AgentRunContext,
        agent_config: AgentConfig,
        messages: tuple[ProviderMessage, ...],
    ) -> GenerateRequest:
        return GenerateRequest(
            model=agent_config.model,
            messages=messages,
            temperature=DEFAULT_TEMPERATURE,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
            workflow_id=context.workflow_id,
            task_id=context.task_id,
            task_attempt=context.task_attempt,
        )

    def _build_messages(
        self,
        *,
        prompt_text: str,
        input: object,
        agent_id: AgentId,
    ) -> tuple[ProviderMessage, ...]:
        if self._stage == AgentStage.TOPIC_SELECTION:
            from agents.types import TopicSelectionInput

            assert isinstance(input, TopicSelectionInput)
            return self._message_builder.build_topic_messages(
                prompt_text=prompt_text,
                input=input,
                agent_id=agent_id,
            )
        if self._stage == AgentStage.SCENARIO_GENERATION:
            from agents.types import ScenarioGenerationInput

            assert isinstance(input, ScenarioGenerationInput)
            return self._message_builder.build_scenario_messages(
                prompt_text=prompt_text,
                input=input,
                agent_id=agent_id,
            )
        from agents.types import CriticInput

        assert isinstance(input, CriticInput)
        return self._message_builder.build_critic_messages(
            prompt_text=prompt_text,
            input=input,
            agent_id=agent_id,
        )

    def _run_pipeline(
        self,
        *,
        context: AgentRunContext,
        input: object,
        build_user_payload: Callable[[object], str],
        validate_input: Callable[[object], None],
        parse_and_validate_output: Callable[[str, str], object],
        emit_stage_outcome: Callable[[AgentRunContext, object], None] | None,
    ) -> object:
        del build_user_payload  # stage payloads are built via MessageBuilder

        agent_config = self._resolve_agent_config(context)
        validate_input(input)

        try:
            prompt = self._prompt_loader.load(agent_config.prompt_file, agent_id=context.agent_id)
        except AgentPromptLoadError:
            raise

        try:
            messages = self._build_messages(
                prompt_text=prompt.text,
                input=input,
                agent_id=context.agent_id,
            )
        except AgentPromptLoadError:
            raise

        telemetry = self._telemetry_factory(context)
        self._current_telemetry = telemetry
        span = telemetry.start_run_span(model=agent_config.model)

        try:
            request = self._build_generate_request(context, agent_config, messages)
            response = context.provider.generate(request)
        except ProviderError as err:
            telemetry.record_validation(result=ValidationResult.FAILED)
            telemetry.log_validation_failed(validation_error_code=err.code)
            telemetry.finalize_span_failure(
                span=span,
                error_class=err.error_class.value,
                retryable=err.retryable,
            )
            raise

        try:
            output = parse_and_validate_output(response.content, prompt.version)
        except AgentOutputValidationError:
            telemetry.record_validation(result=ValidationResult.FAILED)
            telemetry.log_validation_failed(validation_error_code="AGT_OUTPUT")
            telemetry.finalize_span_failure(
                span=span,
                error_class="AGT_OUTPUT",
                retryable=False,
            )
            raise

        telemetry.record_validation(result=ValidationResult.PASSED)
        if emit_stage_outcome is not None:
            emit_stage_outcome(context, output)
        telemetry.log_run_completed(
            model=agent_config.model,
            prompt_version=prompt.version,
            validation_result=ValidationResult.PASSED,
        )
        telemetry.finalize_span_success(span=span)
        return output
