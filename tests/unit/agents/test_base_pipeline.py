"""Pre-code test mold for AGT-009 — BaseAgent pipeline (LLD §7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest

from agents import (
    AgentConfigurationError,
    AgentInputValidationError,
    AgentOutputValidationError,
    AgentPromptLoadError,
    CandidateStory,
    TopicSelectionInput,
    ValidationResult,
)
from config.types import AgentId, ProviderId
from providers import GenerateResponse, ProviderTimeoutError
from providers.types import ProviderMessage, ProviderMessageRole, TokenUsage



@dataclass
class _SpyPromptLoader:
    text: str = "prompt {{candidates_json}}"
    version: str = "promptver01"
    error: BaseException | None = None
    load_calls: int = 0

    def load(self, prompt_file: str, *, agent_id: object) -> object:
        self.load_calls += 1
        if self.error is not None:
            raise self.error
        from agents.prompts.loader import PromptLoadResult

        return PromptLoadResult(text=self.text, version=self.version, path=prompt_file)


@dataclass
class _SpyInputValidator:
    error: BaseException | None = None
    calls: int = 0

    def validate_topic_selection(self, input: TopicSelectionInput) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


@dataclass
class _SpyMessageBuilder:
    error: BaseException | None = None

    def build_topic_messages(
        self,
        *,
        prompt_text: str,
        input: TopicSelectionInput,
        agent_id: object,
    ) -> tuple[object, ...]:
        if self.error is not None:
            raise self.error
        return (
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content=prompt_text),
            ProviderMessage(role=ProviderMessageRole.USER, content="[]"),
        )


@dataclass
class _SpySchemaValidator:
    error: BaseException | None = None
    output: object | None = None

    def parse_provider_content(self, content: str) -> object:
        if self.error is not None:
            raise self.error
        from agents.validation.schema import ParsedProviderPayload

        return ParsedProviderPayload(data={}, raw_length=len(content))

    def validate_topic_output(self, payload: object, *, prompt_version: str) -> object:
        if self.output is not None:
            return self.output
        raise AgentOutputValidationError("missing output")


@dataclass
class _SpyProvider:
    response: GenerateResponse | None = None
    error: BaseException | None = None
    calls: int = 0
    last_request: object | None = None

    @property
    def provider_id(self) -> ProviderId:
        return ProviderId.FAKE

    def generate(self, request: object) -> GenerateResponse:
        self.calls += 1
        self.last_request = request
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@dataclass
class _RecordingTelemetryFactory:
    instances: list[object] = field(default_factory=list)

    def __call__(self, context: object) -> object:
        from agents.base import AgentStage
        from agents.telemetry import RecordingAgentTelemetry

        telemetry = RecordingAgentTelemetry(
            context=context,
            stage=AgentStage.TOPIC_SELECTION,
        )
        self.instances.append(telemetry)
        return telemetry


def _topic_input() -> TopicSelectionInput:
    return TopicSelectionInput(
        candidates=(CandidateStory(source_id="src-1", title="Rust async"),),
    )


def _build_base_agent(**overrides: object) -> object:
    from agents.base import AgentStage, BaseAgent

    prompt_loader = overrides.get("prompt_loader", _SpyPromptLoader())
    input_validator = overrides.get("input_validator", _SpyInputValidator())
    message_builder = overrides.get("message_builder", _SpyMessageBuilder())
    schema_validator = overrides.get("schema_validator", _SpySchemaValidator())
    telemetry_factory = overrides.get("telemetry_factory", _RecordingTelemetryFactory())

    return BaseAgent(
        stage=AgentStage.TOPIC_SELECTION,
        prompt_loader=cast(object, prompt_loader),
        input_validator=cast(object, input_validator),
        message_builder=cast(object, message_builder),
        schema_validator=cast(object, schema_validator),
        telemetry_factory=cast(object, telemetry_factory),
    )


def _run_context(*, provider: object) -> object:
    from agents import AgentRunContext
    from config.app_config import AppConfigFactory
    from config.credentials import CredentialResolver
    from config.draft import (
        AgentDraft,
        BackoffDraft,
        CollectionDraft,
        ConfigDraft,
        FailureInjectionDraft,
        InfrastructureDraft,
        PostgresDraft,
        ProviderDraft,
        RedisDraft,
        RetryPolicyDraft,
        TimeoutDraft,
        WorkerDraft,
        WorkflowDraft,
    )
    from config.types import TaskType
    from observability.fakes import create_fake_bindings
    from observability.settings import _ObservabilityConfig

    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    draft = ConfigDraft(
        config_version="1",
        infrastructure=InfrastructureDraft(
            postgres=PostgresDraft(
                host="localhost",
                port=5432,
                database="cartoon",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisDraft(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/topic_selector.txt",
            ),
        },
        providers={
            ProviderId.FAKE: ProviderDraft(
                api_key_env="FAKE_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=10, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={task: retry_policy for task in TaskType},
        timeouts={
            ProviderId.FAKE: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(enabled=False, active_injections=[]),
    )
    config = AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)
    obs_config = _ObservabilityConfig(
        service_name="agents-pipeline-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    from observability.fakes import create_fake_bindings

    logger, meter, tracer, _correlation = create_fake_bindings(obs_config)
    return AgentRunContext(
        agent_id=AgentId.TOPIC_SELECTOR,
        workflow_id="wf-1",
        task_id="task-1",
        task_attempt=1,
        config=config,
        provider=cast(object, provider),
        logger=logger,
        meter=meter,
        tracer=tracer,
    )


def test_input_validation_failure_exits_before_span_and_metric() -> None:
    """AGT-TC-013: pre-provider input failure has no span or validation metric."""
    telemetry_factory = _RecordingTelemetryFactory()
    agent = _build_base_agent(
        input_validator=_SpyInputValidator(error=AgentInputValidationError("empty candidates")),
        telemetry_factory=telemetry_factory,
    )
    provider = _SpyProvider(
        response=GenerateResponse(
            content="{}",
            model="fake-model",
            provider_id=ProviderId.FAKE,
            latency_ms=1.0,
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        ),
    )

    class _TopicAgentStub:
        def __init__(self) -> None:
            self._agent = agent

        def run(self, *, context: object, input: TopicSelectionInput) -> object:
            return self._agent._run_pipeline(
                context=context,
                input=input,
                build_user_payload=lambda _: "[]",
                validate_input=lambda inp: cast(_SpyInputValidator, agent._input_validator).validate_topic_selection(inp),
                parse_and_validate_output=lambda content, version: object(),
                emit_stage_outcome=lambda ctx, out: None,
            )

    with pytest.raises(AgentInputValidationError):
        _TopicAgentStub().run(context=_run_context(provider=provider), input=_topic_input())

    assert provider.calls == 0
    assert telemetry_factory.instances == []


def test_provider_error_records_validation_failed_before_re_raise() -> None:
    """AGT-TC-031/041: provider failure increments validation metric, no stage outcome."""
    telemetry_factory = _RecordingTelemetryFactory()
    provider = _SpyProvider(error=ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE))
    agent = _build_base_agent(telemetry_factory=telemetry_factory)
    stage_outcome_calls: list[object] = []

    class _TopicAgentStub:
        def __init__(self) -> None:
            self._agent = agent

        def run(self, *, context: object, input: TopicSelectionInput) -> object:
            return self._agent._run_pipeline(
                context=context,
                input=input,
                build_user_payload=lambda _: "[]",
                validate_input=lambda inp: None,
                parse_and_validate_output=lambda content, version: object(),
                emit_stage_outcome=lambda ctx, out: stage_outcome_calls.append(out),
            )

    with pytest.raises(ProviderTimeoutError):
        _TopicAgentStub().run(context=_run_context(provider=provider), input=_topic_input())

    telemetry = telemetry_factory.instances[0]
    assert telemetry.validation_calls == [ValidationResult.FAILED]  # type: ignore[attr-defined]
    assert stage_outcome_calls == []


def test_output_validation_failure_records_failed_before_raise() -> None:
    """AGT-TC-041: output validation failure metric before raise."""
    telemetry_factory = _RecordingTelemetryFactory()
    provider = _SpyProvider(
        response=GenerateResponse(
            content='{"bad":"json"}',
            model="fake-model",
            provider_id=ProviderId.FAKE,
            latency_ms=1.0,
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        ),
    )
    agent = _build_base_agent(
        schema_validator=_SpySchemaValidator(error=AgentOutputValidationError("invalid output")),
        telemetry_factory=telemetry_factory,
    )
    stage_outcome_calls: list[object] = []

    class _TopicAgentStub:
        def __init__(self) -> None:
            self._agent = agent

        def run(self, *, context: object, input: TopicSelectionInput) -> object:
            return self._agent._run_pipeline(
                context=context,
                input=input,
                build_user_payload=lambda _: "[]",
                validate_input=lambda inp: None,
                parse_and_validate_output=lambda content, version: (_ for _ in ()).throw(
                    AgentOutputValidationError("invalid output")
                ),
                emit_stage_outcome=lambda ctx, out: stage_outcome_calls.append(out),
            )

    with pytest.raises(AgentOutputValidationError):
        _TopicAgentStub().run(context=_run_context(provider=provider), input=_topic_input())

    telemetry = telemetry_factory.instances[0]
    assert telemetry.validation_calls == [ValidationResult.FAILED]  # type: ignore[attr-defined]
    assert stage_outcome_calls == []


def test_generate_request_uses_none_temperature_and_max_output_tokens() -> None:
    """CG-AGT-HLD-002: temperature and max_output_tokens remain None."""
    provider = _SpyProvider(
        response=GenerateResponse(
            content='{"outcome":"no_suitable_topic","alternatives":[]}',
            model="fake-model",
            provider_id=ProviderId.FAKE,
            latency_ms=1.0,
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        ),
    )
    agent = _build_base_agent(
        schema_validator=_SpySchemaValidator(
            output=TopicSelectionInput(candidates=()).__class__,  # placeholder replaced below
        ),
    )

    from agents import TopicSelectionOutcome, TopicSelectionOutput

    schema_validator = _SpySchemaValidator(
        output=TopicSelectionOutput(
            outcome=TopicSelectionOutcome.NO_SUITABLE_TOPIC,
            prompt_version="v1",
        ),
    )
    agent = _build_base_agent(schema_validator=schema_validator)

    class _TopicAgentStub:
        def __init__(self) -> None:
            self._agent = agent

        def run(self, *, context: object, input: TopicSelectionInput) -> object:
            return self._agent._run_pipeline(
                context=context,
                input=input,
                build_user_payload=lambda _: "[]",
                validate_input=lambda inp: None,
                parse_and_validate_output=lambda content, version: schema_validator.validate_topic_output(
                    object(), prompt_version=version
                ),
                emit_stage_outcome=lambda ctx, out: None,
            )

    _TopicAgentStub().run(context=_run_context(provider=provider), input=_topic_input())
    request = provider.last_request
    assert request.temperature is None  # type: ignore[attr-defined]
    assert request.max_output_tokens is None  # type: ignore[attr-defined]
    assert request.workflow_id == "wf-1"  # type: ignore[attr-defined]


def test_missing_agent_config_raises_configuration_error() -> None:
    from agents.base import BaseAgent, AgentStage

    agent = BaseAgent(
        stage=AgentStage.TOPIC_SELECTION,
        prompt_loader=cast(object, _SpyPromptLoader()),
        input_validator=cast(object, _SpyInputValidator()),
        message_builder=cast(object, _SpyMessageBuilder()),
        schema_validator=cast(object, _SpySchemaValidator()),
        telemetry_factory=cast(object, _RecordingTelemetryFactory()),
    )
    provider = _SpyProvider(response=None)
    context = _run_context(provider=provider)
    bad_context = type(context)(
        agent_id=AgentId.SCENARIO_GENERATOR,
        workflow_id=context.workflow_id,
        task_id=context.task_id,
        task_attempt=context.task_attempt,
        config=context.config,
        provider=context.provider,
        logger=context.logger,
        meter=context.meter,
        tracer=context.tracer,
    )
    with pytest.raises(AgentConfigurationError):
        agent._resolve_agent_config(bad_context)


def test_unresolved_template_variables_exit_before_span() -> None:
    telemetry_factory = _RecordingTelemetryFactory()
    agent = _build_base_agent(
        message_builder=_SpyMessageBuilder(error=AgentPromptLoadError("unresolved template variables")),
        telemetry_factory=telemetry_factory,
    )
    provider = _SpyProvider(response=None)

    class _TopicAgentStub:
        def __init__(self) -> None:
            self._agent = agent

        def run(self, *, context: object, input: TopicSelectionInput) -> object:
            return self._agent._run_pipeline(
                context=context,
                input=input,
                build_user_payload=lambda _: "[]",
                validate_input=lambda inp: None,
                parse_and_validate_output=lambda content, version: object(),
                emit_stage_outcome=lambda ctx, out: None,
            )

    with pytest.raises(AgentPromptLoadError):
        _TopicAgentStub().run(context=_run_context(provider=provider), input=_topic_input())

    assert provider.calls == 0
    assert telemetry_factory.instances == []
