"""Shared contract-test helpers for agents module (AGT-014, LLD §12)."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
from config.types import AgentId, AppConfig, ProviderId, TaskType
from providers import (
    FakeProvider,
    GenerateRequest,
    GenerateResponse,
    ProviderMessage,
    ProviderMessageRole,
    TokenUsage,
    create_provider,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_ROOT = _REPO_ROOT / "tests" / "fixtures" / "agents"
_PROMPTS_ROOT = _REPO_ROOT / "prompts"


def fixtures_root() -> Path:
    return _FIXTURES_ROOT


def load_output_fixture(name: str) -> str:
    return (_FIXTURES_ROOT / "outputs" / name).read_text(encoding="utf-8")


def load_prompt_fixture(name: str) -> str:
    return (_PROMPTS_ROOT / name).read_text(encoding="utf-8")


def _base_draft(*, prompt_files: Mapping[AgentId, str] | None = None) -> ConfigDraft:
    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    retry = {task: copy.deepcopy(retry_policy) for task in TaskType}
    default_prompts = {
        AgentId.TOPIC_SELECTOR: str(_PROMPTS_ROOT / "topic_selector" / "v1.txt"),
        AgentId.SCENARIO_GENERATOR: str(_PROMPTS_ROOT / "scenario_generator" / "v1.txt"),
        AgentId.CRITIC: str(_PROMPTS_ROOT / "critic" / "v1.txt"),
    }
    if prompt_files:
        default_prompts.update(prompt_files)

    return ConfigDraft(
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
                prompt_file=default_prompts[AgentId.TOPIC_SELECTOR],
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file=default_prompts[AgentId.SCENARIO_GENERATOR],
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file=default_prompts[AgentId.CRITIC],
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
        retry=retry,
        timeouts={
            ProviderId.FAKE: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(enabled=False, active_injections=[]),
    )


def minimal_agents_config(*, prompt_files: Mapping[AgentId, str] | None = None) -> AppConfig:
    draft = _base_draft(prompt_files=prompt_files)
    return AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)


def update_agent_prompt_file(
    config: AppConfig,
    *,
    agent_id: AgentId,
    prompt_file: str,
) -> AppConfig:
    prompt_files = {aid: agent_cfg.prompt_file for aid, agent_cfg in config.agents.items()}
    prompt_files[agent_id] = prompt_file
    return minimal_agents_config(prompt_files=prompt_files)


@dataclass
class CapturingFakeProvider:
    """Wraps FakeProvider and captures the last GenerateRequest."""

    inner: FakeProvider
    requests: list[GenerateRequest]

    @property
    def provider_id(self) -> ProviderId:
        return self.inner.provider_id

    def set_next_response(self, response: GenerateResponse) -> None:
        self.inner.set_next_response(response)

    def set_next_error(self, error: BaseException) -> None:
        self.inner.set_next_error(error)  # type: ignore[arg-type]

    def reset(self) -> None:
        self.inner.reset()

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.requests.append(request)
        return self.inner.generate(request)


def create_capturing_fake_provider(config: AppConfig) -> CapturingFakeProvider:
    provider = create_provider(provider_id=ProviderId.FAKE, config=config)
    assert isinstance(provider, FakeProvider)
    return CapturingFakeProvider(inner=provider, requests=[])


def programmed_agent_response(*, content: str) -> GenerateResponse:
    return GenerateResponse(
        content=content,
        model="fake-model",
        provider_id=ProviderId.FAKE,
        latency_ms=1.0,
        token_usage=TokenUsage(input_tokens=10, output_tokens=20),
    )


def build_agent_run_context(
    *,
    agent_id: AgentId,
    config: AppConfig,
    provider: object,
    logger: object | None = None,
    meter: object | None = None,
    tracer: object | None = None,
) -> object:
    from agents import AgentRunContext
    from observability import get_logger, get_meter, get_tracer

    return AgentRunContext(
        agent_id=agent_id,
        workflow_id="wf-contract-1",
        task_id="task-contract-1",
        task_attempt=1,
        config=config,
        provider=cast(object, provider),
        logger=logger or get_logger(),
        meter=meter or get_meter(),
        tracer=tracer or get_tracer(),
    )


def create_topic_agent_for_contract_tests(**kwargs: object) -> object:
    from agents.base import AgentStage

    return create_agent_for_contract_tests(stage=AgentStage.TOPIC_SELECTION, **kwargs)


def create_scenario_agent_for_contract_tests(**kwargs: object) -> object:
    from agents.base import AgentStage

    return create_agent_for_contract_tests(stage=AgentStage.SCENARIO_GENERATION, **kwargs)


def create_critic_agent_for_contract_tests(**kwargs: object) -> object:
    from agents.base import AgentStage

    return create_agent_for_contract_tests(stage=AgentStage.CRITIC, **kwargs)


def create_agent_for_contract_tests(
    *,
    stage: object,
    prompt_loader: object | None = None,
    schema_validator: object | None = None,
    telemetry_factory: Callable[[object], object] | None = None,
) -> object:
    """Boundary import seam — only callable from conftest per LLD §12.4."""
    from agents.factory import _create_agent_for_tests

    kwargs: dict[str, object] = {"stage": stage}
    if prompt_loader is not None:
        kwargs["prompt_loader"] = prompt_loader
    if schema_validator is not None:
        kwargs["schema_validator"] = schema_validator
    if telemetry_factory is not None:
        kwargs["telemetry_factory"] = telemetry_factory
    return _create_agent_for_tests(**kwargs)  # type: ignore[arg-type]


@contextmanager
def recording_observability() -> Iterator[None]:
    from observability import get_correlation_context
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="agents-contract",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    try:
        with get_correlation_context().bind(
            workflow_id="wf-contract",
            task_id="task-contract",
            task_attempt=1,
        ):
            yield
    finally:
        _reset_observability_state()


def topic_selection_input(*, candidate_count: int = 3) -> object:
    from agents import CandidateStory, TopicSelectionInput

    candidates = tuple(
        CandidateStory(source_id=f"src-{index}", title=f"Story {index}")
        for index in range(candidate_count)
    )
    return TopicSelectionInput(candidates=candidates)


def topic_selected_output_for_scenario() -> object:
    from agents import EvaluationScores, TopicSelectionOutcome, TopicSelectionOutput

    return TopicSelectionOutput(
        outcome=TopicSelectionOutcome.TOPIC_SELECTED,
        prompt_version="topicver01",
        selected_topic="Rust async patterns",
        why_interesting="Developers debate memory safety versus async ergonomics daily",
        cartoon_angle="Two crabs fighting over a shell labeled borrow checker",
        scores=EvaluationScores(
            technical_relevance=0.85,
            developer_relevance=0.9,
            discussion_interest=0.75,
            humour_potential=0.8,
            irony_contradiction=0.6,
            visual_scenario_potential=0.85,
            background_knowledge_required=0.4,
        ),
    )


def scenario_generation_input(*, outcome_not_selected: bool = False) -> object:
    from agents import ScenarioGenerationInput, TopicSelectionOutcome, TopicSelectionOutput

    if outcome_not_selected:
        topic = TopicSelectionOutput(
            outcome=TopicSelectionOutcome.NO_SUITABLE_TOPIC,
            prompt_version="topicver01",
        )
    else:
        topic = topic_selected_output_for_scenario()
    return ScenarioGenerationInput(topic=topic)  # type: ignore[arg-type]


def scenario_output_for_critic() -> object:
    from agents import ScenarioOutput, ScenarioPanel

    return ScenarioOutput(
        topic="Rust async patterns",
        premise="Two developers argue about async runtime choices",
        characters=("Alice", "Bob"),
        panels=(
            ScenarioPanel(scene="Office desk", dialogue="Async is too hard!"),
            ScenarioPanel(scene="Office desk", dialogue="Just use await everywhere!"),
            ScenarioPanel(scene="Office desk", dialogue="That blocks the executor!"),
        ),
        punchline="They both ship blocking I/O anyway.",
        prompt_version="scenariover01",
    )


def critic_input(*, revision_number: int = 1) -> object:
    from agents import CriticInput

    return CriticInput(scenario=scenario_output_for_critic(), revision_number=revision_number)  # type: ignore[arg-type]


def metric_emissions(meter: object) -> list[tuple[str, str, float, dict[str, str]]]:
    return list(meter.emissions)  # type: ignore[attr-defined]
