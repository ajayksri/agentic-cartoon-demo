"""AppConfigFactory and private _ConcreteAppConfig implementation."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from config.credentials import CredentialResolver
from config.draft import (
    AgentDraft,
    ConfigDraft,
    InfrastructureDraft,
    ProviderDraft,
    RetryPolicyDraft,
    TimeoutDraft,
)
from config.types import (
    AgentConfig,
    AgentId,
    AppConfig,
    BackoffConfig,
    CollectionConfig,
    CollectionScoringConfig,
    FailureInjectionConfig,
    InfrastructureConfig,
    InjectionId,
    PostgresConfig,
    ProviderConfig,
    ProviderId,
    ProviderPricing,
    RedisConfig,
    RetryPolicy,
    TaskType,
    TimeoutConfig,
    WorkerConfig,
    WorkflowConfig,
)

_AGENT_CONCURRENCY_FIELDS: Mapping[AgentId, str] = {
    AgentId.TOPIC_SELECTOR: "topic_selector_concurrency",
    AgentId.SCENARIO_GENERATOR: "scenario_generator_concurrency",
    AgentId.CRITIC: "critic_concurrency",
}


def _build_infrastructure(draft: InfrastructureDraft) -> InfrastructureConfig:
    return InfrastructureConfig(
        postgres=PostgresConfig(
            host=draft.postgres.host,
            port=draft.postgres.port,
            database=draft.postgres.database,
            user_env=draft.postgres.user_env,
            password_env=draft.postgres.password_env,
        ),
        redis=RedisConfig(
            host=draft.redis.host,
            port=draft.redis.port,
            db=draft.redis.db,
            password_env=draft.redis.password_env,
        ),
    )


def _build_agent(draft: AgentDraft) -> AgentConfig:
    return AgentConfig(
        provider=draft.provider,
        model=draft.model,
        prompt_file=draft.prompt_file,
    )


def _build_provider(draft: ProviderDraft) -> ProviderConfig:
    pricing = None
    if draft.pricing is not None:
        pricing = ProviderPricing(
            input_per_1k_tokens=draft.pricing.input_per_1k_tokens,
            output_per_1k_tokens=draft.pricing.output_per_1k_tokens,
        )
    return ProviderConfig(
        api_key_env=draft.api_key_env,
        rate_limit_per_minute=draft.rate_limit_per_minute,
        pricing=pricing,
    )


def _build_retry_policy(draft: RetryPolicyDraft) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=draft.max_attempts,
        backoff=BackoffConfig(
            initial_seconds=draft.backoff.initial_seconds,
            multiplier=draft.backoff.multiplier,
            max_seconds=draft.backoff.max_seconds,
        ),
    )


def _build_timeout(draft: TimeoutDraft) -> TimeoutConfig:
    return TimeoutConfig(
        connect_seconds=draft.connect_seconds,
        read_seconds=draft.read_seconds,
        total_seconds=draft.total_seconds,
    )


def _build_failure_injection(draft: ConfigDraft) -> FailureInjectionConfig:
    enabled = draft.failure_injection.enabled
    active_injections = (
        frozenset()
        if not enabled
        else frozenset(draft.failure_injection.active_injections)
    )
    return FailureInjectionConfig(
        enabled=enabled,
        active_injections=active_injections,
    )


class _ConcreteAppConfig(AppConfig):
    """Private implementation; constructed only by AppConfigFactory."""

    def __init__(
        self,
        *,
        infrastructure: InfrastructureConfig,
        agents: Mapping[AgentId, AgentConfig],
        providers: Mapping[ProviderId, ProviderConfig],
        collection: CollectionConfig,
        workflow: WorkflowConfig,
        workers: WorkerConfig,
        retry: Mapping[TaskType, RetryPolicy],
        timeouts: Mapping[ProviderId, TimeoutConfig],
        failure_injection: FailureInjectionConfig,
        credential_resolver: CredentialResolver,
    ) -> None:
        object.__setattr__(self, "infrastructure", infrastructure)
        object.__setattr__(self, "agents", agents)
        object.__setattr__(self, "providers", providers)
        object.__setattr__(self, "collection", collection)
        object.__setattr__(self, "workflow", workflow)
        object.__setattr__(self, "workers", workers)
        object.__setattr__(self, "retry", retry)
        object.__setattr__(self, "timeouts", timeouts)
        object.__setattr__(self, "failure_injection", failure_injection)
        object.__setattr__(self, "_credential_resolver", credential_resolver)

    def get_agent_config(self, agent_id: AgentId) -> AgentConfig:
        return self.agents[agent_id]

    def get_provider_config(self, provider_id: ProviderId) -> ProviderConfig:
        return self.providers[provider_id]

    def get_retry_policy(self, task_type: TaskType) -> RetryPolicy:
        return self.retry[task_type]

    def get_worker_concurrency(self, agent_id: AgentId) -> int:
        field_name = _AGENT_CONCURRENCY_FIELDS[agent_id]
        return getattr(self.workers, field_name)

    def resolve_credential(self, env_var_name: str) -> str:
        return self._credential_resolver.resolve(env_var_name)

    def is_injection_active(self, injection_id: InjectionId) -> bool:
        if not self.failure_injection.enabled:
            return False
        return injection_id in self.failure_injection.active_injections


class AppConfigFactory:
    def __init__(self, *, credential_resolver: CredentialResolver) -> None:
        self._credential_resolver = credential_resolver

    def build(self, draft: ConfigDraft) -> AppConfig:
        scoring = None
        if draft.collection.scoring is not None:
            scoring = CollectionScoringConfig(
                weight_score=draft.collection.scoring.weight_score,
                weight_comments=draft.collection.scoring.weight_comments,
                weight_recency=draft.collection.scoring.weight_recency,
            )

        return _ConcreteAppConfig(
            infrastructure=_build_infrastructure(draft.infrastructure),
            agents=MappingProxyType(
                {agent_id: _build_agent(agent) for agent_id, agent in draft.agents.items()}
            ),
            providers=MappingProxyType(
                {
                    provider_id: _build_provider(provider)
                    for provider_id, provider in draft.providers.items()
                }
            ),
            collection=CollectionConfig(
                candidate_count=draft.collection.candidate_count,
                scoring=scoring,
            ),
            workflow=WorkflowConfig(
                max_scenario_revisions=draft.workflow.max_scenario_revisions,
            ),
            workers=WorkerConfig(
                topic_selector_concurrency=draft.workers.topic_selector_concurrency,
                scenario_generator_concurrency=draft.workers.scenario_generator_concurrency,
                critic_concurrency=draft.workers.critic_concurrency,
            ),
            retry=MappingProxyType(
                {
                    task_type: _build_retry_policy(policy)
                    for task_type, policy in draft.retry.items()
                }
            ),
            timeouts=MappingProxyType(
                {
                    provider_id: _build_timeout(timeout)
                    for provider_id, timeout in draft.timeouts.items()
                }
            ),
            failure_injection=_build_failure_injection(draft),
            credential_resolver=self._credential_resolver,
        )
