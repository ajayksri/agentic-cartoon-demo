"""Pre-code T0 molds for ConfigValidator S3 referential and S4 numeric checks (CFG-008)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from config.errors import ConfigCredentialMissingError, ConfigValueError


def _draft_types() -> tuple[Any, ...]:
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

    return (
        AgentDraft,
        AgentId,
        BackoffDraft,
        CollectionDraft,
        ConfigDraft,
        FailureInjectionDraft,
        InfrastructureDraft,
        InjectionId,
        PostgresDraft,
        ProviderDraft,
        ProviderId,
        RedisDraft,
        RetryPolicyDraft,
        TaskType,
        TimeoutDraft,
        WorkerDraft,
        WorkflowDraft,
    )


def _minimal_valid_draft() -> Any:
    (
        AgentDraft,
        AgentId,
        BackoffDraft,
        CollectionDraft,
        ConfigDraft,
        FailureInjectionDraft,
        InfrastructureDraft,
        InjectionId,
        PostgresDraft,
        ProviderDraft,
        ProviderId,
        RedisDraft,
        RetryPolicyDraft,
        TaskType,
        TimeoutDraft,
        WorkerDraft,
        WorkflowDraft,
    ) = _draft_types()

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
                prompt_file="prompts/topic_selector/v1.txt",
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.OPENAI,
                model="gpt-4",
                prompt_file="prompts/scenario_generator/v1.txt",
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.ANTHROPIC,
                model="claude-3",
                prompt_file="prompts/critic/v1.txt",
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
            active_injections=[],
        ),
    )


def _validator_with_stub_checkers(
    *,
    provider_cred_checker: Any | None = None,
    infra_cred_checker: Any | None = None,
) -> Any:
    from config.validator import ConfigValidator

    class _NoOpChecker:
        def check_all(self, agents: object) -> None:
            return None

        def check_referenced_providers(
            self, agents: object, providers: object
        ) -> None:
            return None

        def check(self, infrastructure: object) -> None:
            return None

    return ConfigValidator(
        prompt_checker=_NoOpChecker(),
        provider_cred_checker=provider_cred_checker or _NoOpChecker(),
        infra_cred_checker=infra_cred_checker or _NoOpChecker(),
    )


def test_s3_agent_references_undefined_provider_raises_config_value_error() -> None:
    """CFG-TC-006 trace: undefined provider reference at S3."""
    from config.types import AgentId, ProviderId

    draft = _minimal_valid_draft()
    draft.agents[AgentId.SCENARIO_GENERATOR].provider = ProviderId.FAKE
    del draft.providers[ProviderId.FAKE]

    validator = _validator_with_stub_checkers()

    with pytest.raises(ConfigValueError) as exc_info:
        validator.validate(draft)

    assert exc_info.value.key_path == "agents.scenario_generator.provider"


def test_s3_unknown_injection_id_raises_config_value_error() -> None:
    """CFG-TC-015 trace: unknown injection ID at S3."""
    draft = _minimal_valid_draft()
    draft.failure_injection.enabled = True
    draft.failure_injection.active_injections = ["FINJ-UNKNOWN"]

    validator = _validator_with_stub_checkers()

    with pytest.raises(ConfigValueError) as exc_info:
        validator.validate(draft)

    assert exc_info.value.key_path.startswith("failure_injection.active_injections")


@pytest.mark.parametrize(
    ("mutator", "expected_key_path"),
    [
        (lambda d: setattr(d.collection, "candidate_count", 0), "collection.candidate_count"),
        (
            lambda d: setattr(d.collection, "candidate_count", -1),
            "collection.candidate_count",
        ),
        (
            lambda d: setattr(d.workflow, "max_scenario_revisions", 0),
            "workflow.max_scenario_revisions",
        ),
        (
            lambda d: setattr(d.workers, "topic_selector_concurrency", 0),
            "workers.topic_selector_concurrency",
        ),
        (
            lambda d: setattr(
                d.retry[next(iter(d.retry))], "max_attempts", 0
            ),
            "retry.",
        ),
        (
            lambda d: setattr(
                d.retry[next(iter(d.retry))].backoff, "initial_seconds", 0
            ),
            "retry.",
        ),
        (
            lambda d: setattr(
                d.timeouts[next(iter(d.timeouts))], "read_seconds", 0
            ),
            "timeouts.",
        ),
        (
            lambda d: setattr(
                d.timeouts[next(iter(d.timeouts))], "connect_seconds", 0
            ),
            "connect_seconds",
        ),
        (
            lambda d: setattr(
                d.timeouts[next(iter(d.timeouts))], "total_seconds", -1
            ),
            "total_seconds",
        ),
        (
            lambda d: setattr(
                list(d.providers.values())[0], "rate_limit_per_minute", 0
            ),
            "providers.",
        ),
    ],
    ids=[
        "zero_candidate_count",
        "negative_candidate_count",
        "zero_max_scenario_revisions",
        "zero_worker_concurrency",
        "zero_retry_max_attempts",
        "zero_backoff_initial_seconds",
        "zero_timeout_read_seconds",
        "zero_connect_seconds",
        "negative_total_seconds",
        "zero_rate_limit_per_minute",
    ],
)
def test_s4_invalid_numeric_constraints_raise_config_value_error(
    mutator: Any, expected_key_path: str
) -> None:
    """CFG-TC-006/007/010/011 trace: S4 numeric table cases."""
    draft = _minimal_valid_draft()
    mutator(draft)
    validator = _validator_with_stub_checkers()

    with pytest.raises(ConfigValueError) as exc_info:
        validator.validate(draft)

    assert expected_key_path in exc_info.value.key_path


def test_validate_success_returns_same_draft_unchanged() -> None:
    """Validator must not mutate draft on success path."""
    draft = _minimal_valid_draft()
    validator = _validator_with_stub_checkers()

    result = validator.validate(draft)

    assert result is draft


def test_s6_provider_cred_checker_failure_propagates() -> None:
    """S6: injected provider checker failure propagates through validate()."""

    class _RaisingProviderCredChecker:
        def check_referenced_providers(
            self, agents: object, providers: object
        ) -> None:
            raise ConfigCredentialMissingError(
                "missing OPENAI_API_KEY",
                env_var_name="OPENAI_API_KEY",
            )

    draft = _minimal_valid_draft()
    validator = _validator_with_stub_checkers(
        provider_cred_checker=_RaisingProviderCredChecker(),
    )

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        validator.validate(draft)

    assert exc_info.value.code == "CFG_CREDENTIAL"
    assert exc_info.value.env_var_name == "OPENAI_API_KEY"


def test_s6_infra_cred_checker_failure_propagates() -> None:
    """S6: injected infra checker failure propagates through validate()."""

    class _RaisingInfraCredChecker:
        def check(self, infrastructure: object) -> None:
            raise ConfigCredentialMissingError(
                "missing POSTGRES_USER",
                env_var_name="POSTGRES_USER",
            )

    draft = _minimal_valid_draft()
    validator = _validator_with_stub_checkers(
        infra_cred_checker=_RaisingInfraCredChecker(),
    )

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        validator.validate(draft)

    assert exc_info.value.code == "CFG_CREDENTIAL"
    assert exc_info.value.env_var_name == "POSTGRES_USER"
