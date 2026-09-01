"""Pre-code T0 molds for AppConfigFactory and _ConcreteAppConfig (CFG-009)."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from typing import Any
import pytest


def _minimal_valid_draft() -> Any:
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
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/topic_selector.txt",
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.OPENAI,
                model="gpt-4",
                prompt_file="prompts/scenario_generator.txt",
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.ANTHROPIC,
                model="claude-3",
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
            ProviderId.FAKE: ProviderDraft(
                api_key_env="FAKE_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=10, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=2,
            scenario_generator_concurrency=3,
            critic_concurrency=1,
        ),
        retry=retry,
        timeouts={
            ProviderId.OPENAI: TimeoutDraft(
                connect_seconds=None, read_seconds=60.0, total_seconds=None
            ),
            ProviderId.ANTHROPIC: TimeoutDraft(
                connect_seconds=None, read_seconds=60.0, total_seconds=None
            ),
            ProviderId.GEMINI: TimeoutDraft(
                connect_seconds=None, read_seconds=60.0, total_seconds=None
            ),
        },
        failure_injection=FailureInjectionDraft(
            enabled=False,
            active_injections=[InjectionId.FINJ_WKR_PRE],
        ),
    )


def _build_app_config(draft: Any | None = None) -> Any:
    from config.app_config import AppConfigFactory
    from config.credentials import CredentialResolver

    factory = AppConfigFactory(credential_resolver=CredentialResolver())
    return factory.build(draft or _minimal_valid_draft())


def test_build_returns_frozen_app_config() -> None:
    """CFG-TC-022 trace: built AppConfig and nested types are frozen."""
    from config.types import AgentId, TaskType

    app_config = _build_app_config()

    with pytest.raises(FrozenInstanceError):
        app_config.collection.candidate_count = 99  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        app_config.agents[AgentId.TOPIC_SELECTOR].model = "mutated"  # type: ignore[misc]

    with pytest.raises(TypeError):
        app_config.retry[TaskType.COLLECT] = app_config.retry[TaskType.SELECT_TOPIC]  # type: ignore[index]


def test_is_injection_active_false_when_disabled_with_nonempty_list() -> None:
    """CFG-TC-015 trace: disabled injection ignores active_injections list."""
    from config.types import InjectionId

    draft = _minimal_valid_draft()
    draft.failure_injection.enabled = False
    draft.failure_injection.active_injections = [InjectionId.FINJ_WKR_PRE]

    app_config = _build_app_config(draft)

    assert app_config.is_injection_active(InjectionId.FINJ_WKR_PRE) is False
    assert app_config.is_injection_active(InjectionId.FINJ_Q_DUP) is False


def test_is_injection_active_true_for_listed_ids_when_enabled() -> None:
    """CFG-TC-014 trace: enabled injection selective activation."""
    from config.types import InjectionId

    draft = _minimal_valid_draft()
    draft.failure_injection.enabled = True
    draft.failure_injection.active_injections = [
        InjectionId.FINJ_WKR_PRE,
        InjectionId.FINJ_Q_DUP,
    ]

    app_config = _build_app_config(draft)

    assert app_config.is_injection_active(InjectionId.FINJ_WKR_PRE) is True
    assert app_config.is_injection_active(InjectionId.FINJ_Q_DUP) is True
    assert app_config.is_injection_active(InjectionId.FINJ_PRV_ERROR) is False


def test_get_worker_concurrency_maps_agent_ids() -> None:
    """CFG-TC-008 trace: AgentId to WorkerConfig field mapping."""
    from config.types import AgentId

    app_config = _build_app_config()

    assert app_config.get_worker_concurrency(AgentId.TOPIC_SELECTOR) == 2
    assert app_config.get_worker_concurrency(AgentId.SCENARIO_GENERATOR) == 3
    assert app_config.get_worker_concurrency(AgentId.CRITIC) == 1


def test_resolve_credential_delegates_without_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CFG-TC-024 trace: resolve_credential delegates to CredentialResolver."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-value")
    app_config = _build_app_config()

    assert app_config.resolve_credential("OPENAI_API_KEY") == "test-value"


def test_resolve_credential_uses_injected_resolver() -> None:
    """AppConfigFactory delegates resolve_credential to injected CredentialResolver."""
    from config.app_config import AppConfigFactory

    class _FakeResolver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def resolve(self, env_var_name: str) -> str:
            self.calls.append(env_var_name)
            return "fake-value"

    fake = _FakeResolver()
    factory = AppConfigFactory(credential_resolver=fake)  # type: ignore[arg-type]
    app_config = factory.build(_minimal_valid_draft())

    assert app_config.resolve_credential("TEST_VAR") == "fake-value"
    assert fake.calls == ["TEST_VAR"]


def test_build_does_not_expose_config_version_on_app_config() -> None:
    """config_version is load-time metadata only (LLD §6.9)."""
    app_config = _build_app_config()

    assert not hasattr(app_config, "config_version")
