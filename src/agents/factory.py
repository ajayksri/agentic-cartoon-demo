"""Internal agent construction router (not exported from package)."""

from __future__ import annotations

from collections.abc import Callable

from agents.agents.critic import CriticAgentImpl
from agents.agents.scenario import ScenarioGenerationAgentImpl
from agents.agents.topic import TopicSelectionAgentImpl
from agents.base import AgentStage, BaseAgent
from agents.prompts.builder import MessageBuilder
from agents.prompts.loader import PromptLoader
from agents.telemetry import AgentTelemetry
from agents.types import AgentRunContext
from agents.validation.input import InputValidator
from agents.validation.schema import SchemaValidator


class AgentFactory:
    """Constructs agent implementation instances with default collaborators."""

    def __init__(
        self,
        *,
        prompt_loader: PromptLoader | None = None,
        input_validator: InputValidator | None = None,
        schema_validator: SchemaValidator | None = None,
        message_builder: MessageBuilder | None = None,
        telemetry_factory: Callable[[AgentRunContext], AgentTelemetry] | None = None,
    ) -> None:
        self._prompt_loader = prompt_loader or PromptLoader()
        self._input_validator = input_validator or InputValidator()
        self._schema_validator = schema_validator or SchemaValidator()
        self._message_builder = message_builder or MessageBuilder()
        self._telemetry_factory = telemetry_factory

    def _default_telemetry_factory(self, stage: AgentStage) -> Callable[[AgentRunContext], AgentTelemetry]:
        def _factory(context: AgentRunContext) -> AgentTelemetry:
            return AgentTelemetry(context=context, stage=stage)

        return _factory

    def _build_base_kwargs(self, stage: AgentStage) -> dict[str, object]:
        telemetry_factory = self._telemetry_factory or self._default_telemetry_factory(stage)
        return {
            "stage": stage,
            "prompt_loader": self._prompt_loader,
            "input_validator": self._input_validator,
            "message_builder": self._message_builder,
            "schema_validator": self._schema_validator,
            "telemetry_factory": telemetry_factory,
        }

    def create_topic_selector(self) -> TopicSelectionAgentImpl:
        return TopicSelectionAgentImpl(**self._build_base_kwargs(AgentStage.TOPIC_SELECTION))  # type: ignore[arg-type]

    def create_scenario_generator(self) -> ScenarioGenerationAgentImpl:
        return ScenarioGenerationAgentImpl(**self._build_base_kwargs(AgentStage.SCENARIO_GENERATION))  # type: ignore[arg-type]

    def create_critic(self) -> CriticAgentImpl:
        return CriticAgentImpl(**self._build_base_kwargs(AgentStage.CRITIC))  # type: ignore[arg-type]


def _create_agent_for_tests(
    *,
    stage: AgentStage,
    prompt_loader: PromptLoader | None = None,
    schema_validator: SchemaValidator | None = None,
    telemetry_factory: Callable[[AgentRunContext], AgentTelemetry] | None = None,
) -> TopicSelectionAgentImpl | ScenarioGenerationAgentImpl | CriticAgentImpl:
    factory = AgentFactory(
        prompt_loader=prompt_loader,
        schema_validator=schema_validator,
        telemetry_factory=telemetry_factory,
    )
    if stage == AgentStage.TOPIC_SELECTION:
        return factory.create_topic_selector()
    if stage == AgentStage.SCENARIO_GENERATION:
        return factory.create_scenario_generator()
    return factory.create_critic()
