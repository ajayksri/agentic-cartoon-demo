"""Smoke tests for internal draft dataclasses (CFG-001)."""

from __future__ import annotations

from decimal import Decimal

from config.draft import (
    AgentDraft,
    BackoffDraft,
    CollectionDraft,
    CollectionScoringDraft,
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
from config.types import AgentId, InjectionId, ProviderId, TaskType


def test_postgres_draft_field_access() -> None:
    draft = PostgresDraft(
        host="localhost",
        port=5432,
        database="cartoon",
        user_env="POSTGRES_USER",
        password_env="POSTGRES_PASSWORD",
    )
    assert draft.host == "localhost"
    assert draft.port == 5432


def test_redis_draft_optional_password_env() -> None:
    draft = RedisDraft(host="localhost", port=6379, db=0, password_env=None)
    assert draft.password_env is None


def test_infrastructure_draft_nesting() -> None:
    draft = InfrastructureDraft(
        postgres=PostgresDraft(
            host="localhost",
            port=5432,
            database="cartoon",
            user_env="POSTGRES_USER",
            password_env="POSTGRES_PASSWORD",
        ),
        redis=RedisDraft(host="localhost", port=6379, db=0, password_env=None),
    )
    assert draft.postgres.database == "cartoon"
    assert draft.redis.db == 0


def test_agent_draft_uses_public_enums() -> None:
    draft = AgentDraft(
        provider=ProviderId.OPENAI,
        model="gpt-4",
        prompt_file="prompts/topic.txt",
    )
    assert draft.provider is ProviderId.OPENAI


def test_provider_draft_optional_pricing() -> None:
    draft = ProviderDraft(
        api_key_env="OPENAI_API_KEY",
        rate_limit_per_minute=60,
        pricing=ProviderPricingDraft(
            input_per_1k_tokens=Decimal("0.01"),
            output_per_1k_tokens=None,
        ),
    )
    assert draft.pricing is not None
    assert draft.pricing.output_per_1k_tokens is None


def test_collection_draft_optional_scoring() -> None:
    draft = CollectionDraft(
        candidate_count=10,
        scoring=CollectionScoringDraft(
            weight_score=0.5,
            weight_comments=0.3,
            weight_recency=0.2,
        ),
    )
    assert draft.candidate_count == 10
    assert draft.scoring is not None
    assert draft.scoring.weight_score == 0.5


def test_workflow_and_worker_drafts() -> None:
    workflow = WorkflowDraft(max_scenario_revisions=3)
    workers = WorkerDraft(
        topic_selector_concurrency=2,
        scenario_generator_concurrency=1,
        critic_concurrency=1,
    )
    assert workflow.max_scenario_revisions == 3
    assert workers.critic_concurrency == 1


def test_retry_policy_draft_backoff_nesting() -> None:
    draft = RetryPolicyDraft(
        max_attempts=3,
        backoff=BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0),
    )
    assert draft.backoff.multiplier == 2.0


def test_timeout_draft_optional_connect_and_total() -> None:
    draft = TimeoutDraft(connect_seconds=None, read_seconds=30.0, total_seconds=None)
    assert draft.read_seconds == 30.0
    assert draft.connect_seconds is None


def test_failure_injection_draft_active_list() -> None:
    draft = FailureInjectionDraft(
        enabled=True,
        active_injections=[InjectionId.FINJ_WKR_PRE],
    )
    assert draft.enabled is True
    assert draft.active_injections == [InjectionId.FINJ_WKR_PRE]


def test_config_draft_aggregates_all_domains() -> None:
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
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/topic.txt",
            ),
        },
        providers={
            ProviderId.GEMINI: ProviderDraft(
                api_key_env="GEMINI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=5, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicyDraft(
                max_attempts=1,
                backoff=BackoffDraft(
                    initial_seconds=1.0,
                    multiplier=2.0,
                    max_seconds=10.0,
                ),
            ),
        },
        timeouts={
            ProviderId.GEMINI: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(enabled=False, active_injections=[]),
    )
    assert draft.config_version == "1"
    assert draft.agents[AgentId.TOPIC_SELECTOR].model == "gemini-pro"
    assert draft.failure_injection.enabled is False
