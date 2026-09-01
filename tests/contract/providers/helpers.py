"""Shared contract-test helpers for providers module (PRV-018, LLD §7, §15.4)."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

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
    ProviderPricingDraft,
    RedisDraft,
    RetryPolicyDraft,
    TimeoutDraft,
    WorkerDraft,
    WorkflowDraft,
)
from config.types import (
    AgentId,
    AppConfig,
    InjectionId,
    ProviderId,
    ProviderPricing,
    TaskType,
)
from providers import (
    GenerateRequest,
    GenerateResponse,
    ProviderMessage,
    ProviderMessageRole,
    TokenUsage,
)


class CredentialResolveSpy:
    """Tracks env var names requested via AppConfig.resolve_credential."""

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self.requests: list[str] = []
        self._values = dict(values or {})

    def resolve(self, env_var_name: str) -> str:
        self.requests.append(env_var_name)
        if env_var_name not in self._values:
            raise KeyError(env_var_name)
        return self._values[env_var_name]


def _base_draft() -> ConfigDraft:
    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    retry = {task: copy.deepcopy(retry_policy) for task in TaskType}

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
                provider=ProviderId.OPENAI,
                model="gpt-4",
                prompt_file="prompts/topic_selector.txt",
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.ANTHROPIC,
                model="claude-3",
                prompt_file="prompts/scenario_generator.txt",
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/critic.txt",
            ),
        },
        providers={
            ProviderId.OPENAI: ProviderDraft(
                api_key_env="OPENAI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
            ProviderId.ANTHROPIC: ProviderDraft(
                api_key_env="ANTHROPIC_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
            ProviderId.GEMINI: ProviderDraft(
                api_key_env="GEMINI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
            ProviderId.KIMI: ProviderDraft(
                api_key_env="MOONSHOT_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
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
            provider_id: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            )
            for provider_id in (
                ProviderId.OPENAI,
                ProviderId.ANTHROPIC,
                ProviderId.GEMINI,
                ProviderId.KIMI,
                ProviderId.FAKE,
            )
        },
        failure_injection=FailureInjectionDraft(
            enabled=False,
            active_injections=[],
        ),
    )


def minimal_provider_config(
    *,
    openai_only_agents: bool = False,
    fake_rate_limit_per_minute: int | None = None,
    openai_pricing: ProviderPricing | None = None,
    failure_injection_enabled: bool = False,
    active_injections: frozenset[InjectionId] = frozenset(),
    openai_read_seconds: float = 60.0,
    credential_resolver: CredentialResolveSpy | CredentialResolver | None = None,
) -> AppConfig:
    """Valid AppConfig with all provider domains for contract tests."""
    draft = _base_draft()

    if openai_only_agents:
        draft.agents = {
            AgentId.TOPIC_SELECTOR: AgentDraft(
                provider=ProviderId.OPENAI,
                model="gpt-4",
                prompt_file="prompts/topic_selector.txt",
            ),
        }

    if fake_rate_limit_per_minute is not None:
        fake = draft.providers[ProviderId.FAKE]
        draft.providers[ProviderId.FAKE] = ProviderDraft(
            api_key_env=fake.api_key_env,
            rate_limit_per_minute=fake_rate_limit_per_minute,
            pricing=fake.pricing,
        )

    if openai_pricing is not None:
        openai = draft.providers[ProviderId.OPENAI]
        draft.providers[ProviderId.OPENAI] = ProviderDraft(
            api_key_env=openai.api_key_env,
            rate_limit_per_minute=openai.rate_limit_per_minute,
            pricing=ProviderPricingDraft(
                input_per_1k_tokens=openai_pricing.input_per_1k_tokens,
                output_per_1k_tokens=openai_pricing.output_per_1k_tokens,
            ),
        )

    draft.timeouts[ProviderId.OPENAI] = TimeoutDraft(
        connect_seconds=None,
        read_seconds=openai_read_seconds,
        total_seconds=None,
    )
    draft.failure_injection = FailureInjectionDraft(
        enabled=failure_injection_enabled,
        active_injections=sorted(active_injections),
    )

    resolver = credential_resolver or CredentialResolver()
    factory = AppConfigFactory(credential_resolver=resolver)
    return factory.build(draft)


def valid_generate_request(**overrides: object) -> GenerateRequest:
    """Minimal valid GenerateRequest for contract tests."""
    defaults: dict[str, object] = {
        "model": "gpt-4",
        "messages": (
            ProviderMessage(role=ProviderMessageRole.USER, content="contract prompt"),
        ),
        "workflow_id": "wf-contract-1",
        "task_id": "task-contract-1",
        "task_attempt": 1,
    }
    defaults.update(overrides)
    return GenerateRequest(**defaults)  # type: ignore[arg-type]


def programmed_fake_response(**overrides: object) -> GenerateResponse:
    """GenerateResponse suitable for FakeProvider programming."""
    defaults: dict[str, object] = {
        "content": "programmed content",
        "model": "fake-model",
        "provider_id": ProviderId.FAKE,
        "latency_ms": 2.5,
        "token_usage": TokenUsage(input_tokens=100, output_tokens=50),
        "estimated_cost_usd": Decimal("0.001500"),
    }
    defaults.update(overrides)
    return GenerateResponse(**defaults)  # type: ignore[arg-type]


def make_stub_transport(**kwargs: object) -> object:
    """Build StubVendorTransport without importing it in contract test modules."""
    from providers.vendors._transport import StubVendorTransport

    return StubVendorTransport(**kwargs)  # type: ignore[arg-type]


def stub_success_result(*, content: str = "stub success", token_usage: TokenUsage | None = None) -> object:
    from providers.vendors._transport import VendorCallResult

    return VendorCallResult(
        content=content,
        model="gpt-4",
        token_usage=token_usage,
    )


def stub_failure_signal(**kwargs: object) -> object:
    from providers.vendors._transport import VendorFailureSignal

    return VendorFailureSignal(**kwargs)  # type: ignore[arg-type]


def generate_with_stub_transport(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    transport: object,
    request: GenerateRequest,
    registry: object | None = None,
) -> GenerateResponse:
    """Injection seam per LLD §7 — boundary import allowed here only."""
    from providers.factory import _create_provider_for_tests

    provider = _create_provider_for_tests(
        provider_id=provider_id,
        config=config,
        transport=transport,
        registry=registry,
    )
    return provider.generate(request)


def create_fake_provider(config: AppConfig, *, registry: object | None = None) -> object:
    """Return FakeProvider via public create_provider factory."""
    from providers import FakeProvider, create_provider

    provider = create_provider(provider_id=ProviderId.FAKE, config=config, registry=registry)
    assert isinstance(provider, FakeProvider)
    return provider


def build_finj_registry(
    config: AppConfig,
    *,
    hooks: Mapping[InjectionId, Callable[[], None]] | None = None,
) -> object:
    """Construct failure_injection registry with optional FINJ hooks."""
    import failure_injection

    class _FunctionHook:
        def __init__(self, fn: Callable[[object | None], None]) -> None:
            self._fn = fn

        def invoke(self, context: object | None = None) -> None:
            self._fn(context)

    registry = failure_injection.create_failure_injection_registry(config)
    for injection_id, hook in (hooks or {}).items():
        registry.register_hook(injection_id, _FunctionHook(hook))
    return registry


@contextmanager
def recording_observability() -> Iterator[None]:
    """Reset observability and wire in-memory fakes for PRV-TC-060."""
    from observability import get_correlation_context
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="providers-contract",
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


def generate_with_recording_telemetry(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    request: GenerateRequest,
    transport: object | None = None,
    registry: object | None = None,
) -> tuple[GenerateResponse, object]:
    """Run generate with RecordingTelemetry injected via test seam."""
    from providers.factory import _create_provider_for_tests
    from providers.telemetry import RecordingTelemetry

    telemetry = RecordingTelemetry(provider_id=provider_id)
    kwargs: dict[str, object] = {
        "provider_id": provider_id,
        "config": config,
        "registry": registry,
        "telemetry": telemetry,
    }
    if transport is not None:
        kwargs["transport"] = transport
    provider = _create_provider_for_tests(**kwargs)  # type: ignore[arg-type]
    response = provider.generate(request)
    return response, telemetry


def setup_recording_provider(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    transport: object | None = None,
    registry: object | None = None,
) -> tuple[object, object]:
    """Return provider and RecordingTelemetry for failure-path assertions."""
    from providers.factory import _create_provider_for_tests
    from providers.telemetry import RecordingTelemetry

    telemetry = RecordingTelemetry(provider_id=provider_id)
    kwargs: dict[str, object] = {
        "provider_id": provider_id,
        "config": config,
        "registry": registry,
        "telemetry": telemetry,
    }
    if transport is not None:
        kwargs["transport"] = transport
    provider = _create_provider_for_tests(**kwargs)  # type: ignore[arg-type]
    return provider, telemetry
