"""Unit tests for CFG-007 — Credential checkers and resolver (S6)."""

from __future__ import annotations

import pytest

from config.credentials import (
    CredentialResolver,
    InfraCredChecker,
    ProviderCredChecker,
)
from config.draft import (
    AgentDraft,
    InfrastructureDraft,
    PostgresDraft,
    ProviderDraft,
    RedisDraft,
)
from config.errors import ConfigCredentialMissingError
from config.messages import credential_message
from config.types import AgentId, ProviderId


def _sample_agents_and_providers() -> tuple[dict[AgentId, AgentDraft], dict[ProviderId, ProviderDraft]]:
    agents = {
        AgentId.TOPIC_SELECTOR: AgentDraft(
            provider=ProviderId.GEMINI,
            model="gemini-pro",
            prompt_file="prompts/topic.txt",
        ),
        AgentId.SCENARIO_GENERATOR: AgentDraft(
            provider=ProviderId.OPENAI,
            model="gpt-4",
            prompt_file="prompts/scenario.txt",
        ),
        AgentId.CRITIC: AgentDraft(
            provider=ProviderId.ANTHROPIC,
            model="claude-3",
            prompt_file="prompts/critic.txt",
        ),
    }
    providers = {
        ProviderId.OPENAI: ProviderDraft(api_key_env="OPENAI_API_KEY", rate_limit_per_minute=None, pricing=None),
        ProviderId.ANTHROPIC: ProviderDraft(api_key_env="ANTHROPIC_API_KEY", rate_limit_per_minute=None, pricing=None),
        ProviderId.GEMINI: ProviderDraft(api_key_env="GEMINI_API_KEY", rate_limit_per_minute=None, pricing=None),
        ProviderId.FAKE: ProviderDraft(api_key_env="FAKE_API_KEY", rate_limit_per_minute=None, pricing=None),
    }
    return agents, providers


def _sample_infrastructure(*, redis_password_env: str | None = None) -> InfrastructureDraft:
    return InfrastructureDraft(
        postgres=PostgresDraft(
            host="localhost",
            port=5432,
            database="cartoon",
            user_env="POSTGRES_USER",
            password_env="POSTGRES_PASSWORD",
        ),
        redis=RedisDraft(
            host="localhost",
            port=6379,
            db=0,
            password_env=redis_password_env,
        ),
    )


def test_referenced_provider_missing_env_raises_credential_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-TC-023: missing credential for configured provider names env var only."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "set")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "set")

    agents, providers = _sample_agents_and_providers()
    checker = ProviderCredChecker()

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        checker.check_referenced_providers(agents, providers)

    assert exc_info.value.code == "CFG_CREDENTIAL"
    assert exc_info.value.env_var_name == "OPENAI_API_KEY"
    assert str(exc_info.value) == credential_message(env_var_name="OPENAI_API_KEY")
    assert "sk-" not in str(exc_info.value)


def test_unreferenced_provider_does_not_require_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-TC-004: only gemini referenced — unset OPENAI/ANTHROPIC must not fail."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    agents = {
        AgentId.TOPIC_SELECTOR: AgentDraft(
            provider=ProviderId.GEMINI,
            model="gemini-pro",
            prompt_file="prompts/topic.txt",
        ),
    }
    providers = {
        ProviderId.OPENAI: ProviderDraft(api_key_env="OPENAI_API_KEY", rate_limit_per_minute=None, pricing=None),
        ProviderId.ANTHROPIC: ProviderDraft(api_key_env="ANTHROPIC_API_KEY", rate_limit_per_minute=None, pricing=None),
        ProviderId.GEMINI: ProviderDraft(api_key_env="GEMINI_API_KEY", rate_limit_per_minute=None, pricing=None),
    }
    checker = ProviderCredChecker()

    checker.check_referenced_providers(agents, providers)


def test_postgres_infra_credentials_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Postgres user_env and password_env must be non-empty in environment."""
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "set")

    checker = InfraCredChecker()

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        checker.check(_sample_infrastructure())

    assert exc_info.value.code == "CFG_CREDENTIAL"
    assert exc_info.value.env_var_name == "POSTGRES_USER"


def test_redis_password_env_skipped_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis password_env check skipped when password_env is None (LLD §7.1 default)."""
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")

    checker = InfraCredChecker()

    checker.check(_sample_infrastructure(redis_password_env=None))


def test_redis_password_env_required_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis password_env must be set when configured non-None."""
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    checker = InfraCredChecker()

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        checker.check(_sample_infrastructure(redis_password_env="REDIS_PASSWORD"))

    assert exc_info.value.env_var_name == "REDIS_PASSWORD"


def test_credential_resolver_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-TC-024: CredentialResolver returns environment value when set."""
    monkeypatch.setenv("OPENAI_API_KEY", "resolved-value")

    resolver = CredentialResolver()
    assert resolver.resolve("OPENAI_API_KEY") == "resolved-value"


def test_credential_resolver_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-TC-025: empty/missing env → ConfigCredentialMissingError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resolver = CredentialResolver()

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        resolver.resolve("OPENAI_API_KEY")

    assert exc_info.value.code == "CFG_CREDENTIAL"
    assert exc_info.value.env_var_name == "OPENAI_API_KEY"
    assert str(exc_info.value) == credential_message(env_var_name="OPENAI_API_KEY")


def test_credential_resolver_raises_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty string env value treated as missing credential."""
    monkeypatch.setenv("OPENAI_API_KEY", "")

    resolver = CredentialResolver()

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        resolver.resolve("OPENAI_API_KEY")

    assert exc_info.value.env_var_name == "OPENAI_API_KEY"
