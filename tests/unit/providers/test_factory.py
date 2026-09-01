"""Pre-code test mold for PRV-014 — create_provider factory (LLD §4.1, §7)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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
from config.types import AgentId, InjectionId, ProviderId, TaskType
from providers import FakeProvider, ModelProvider, ProviderConfigurationError, create_provider

def _factory_config_draft() -> ConfigDraft:
    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    retry = {task: retry_policy for task in TaskType}

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
            active_injections=[InjectionId.FINJ_WKR_PRE],
        ),
    )
def _build_config(*, resolver: CredentialResolver | None = None) -> object:
    factory = AppConfigFactory(
        credential_resolver=resolver or CredentialResolver(),
    )
    return factory.build(_factory_config_draft())
@pytest.mark.parametrize(
    "provider_id",
    [ProviderId.OPENAI, ProviderId.ANTHROPIC, ProviderId.GEMINI, ProviderId.KIMI, ProviderId.FAKE],
)
def test_create_provider_returns_model_provider_for_each_id(
    provider_id: ProviderId,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ProviderId constructs adapter with matching provider_id property."""
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    config = _build_config()

    provider = create_provider(provider_id=provider_id, config=config)

    assert isinstance(provider, ModelProvider)
    assert provider.provider_id == provider_id
def test_create_provider_returns_new_instance_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CG-PRV-007: successive create_provider calls return distinct instances."""
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    config = _build_config()

    first = create_provider(provider_id=ProviderId.OPENAI, config=config)
    second = create_provider(provider_id=ProviderId.OPENAI, config=config)

    assert first is not second
def test_create_provider_fake_satisfies_fake_provider_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_provider(FAKE) returns object with programming API (PRV-TC-031 seam)."""
    config = _build_config()

    provider = create_provider(provider_id=ProviderId.FAKE, config=config)

    assert isinstance(provider, FakeProvider)
    assert callable(provider.set_next_response)
    assert callable(provider.set_next_error)
    assert callable(provider.reset)
def test_missing_credential_error_omits_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRV-TC-061: configuration error names env var only, never secret value."""
    secret = "super-secret-openai-key-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    config = _build_config()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_provider(provider_id=ProviderId.OPENAI, config=config)

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert secret not in message
def test_missing_timeout_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing timeouts entry raises ProviderConfigurationError naming provider."""
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    draft = _factory_config_draft()
    draft.timeouts = {
        provider_id: TimeoutDraft(
            connect_seconds=None,
            read_seconds=60.0,
            total_seconds=None,
        )
        for provider_id in (ProviderId.ANTHROPIC, ProviderId.GEMINI, ProviderId.KIMI, ProviderId.FAKE)
    }
    config = AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)

    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_provider(provider_id=ProviderId.OPENAI, config=config)

    assert "openai" in str(exc_info.value).lower()
def test_create_provider_for_tests_accepts_stub_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contract seam injects StubVendorTransport without vendor SDK."""
    from providers import GenerateRequest, ProviderMessage, ProviderMessageRole
    from providers.factory import _create_provider_for_tests
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    config = _build_config()
    stub = StubVendorTransport(
        result=VendorCallResult(content="stubbed", model="gpt-4", token_usage=None),
    )
    provider = _create_provider_for_tests(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=stub,
    )
    request = GenerateRequest(
        model="gpt-4",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hi"),),
    )

    response = provider.generate(request)

    assert response.content == "stubbed"
def test_factory_module_has_no_vendor_sdk_imports() -> None:
    """factory.py must not import openai, anthropic, or google.genai."""
    factory_path = Path(__file__).resolve().parents[3] / "src" / "providers" / "factory.py"
    source = factory_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"openai", "anthropic", "google"}
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert imports.isdisjoint(forbidden)
