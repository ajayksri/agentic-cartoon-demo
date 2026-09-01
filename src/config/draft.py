"""Internal mutable draft dataclasses for the config load pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from config.types import AgentId, InjectionId, ProviderId, TaskType

RawConfigTree = dict[str, object]
RawNode = dict[str, object] | list[object] | str | int | float | bool | None


@dataclass
class PostgresDraft:
    host: str
    port: int
    database: str
    user_env: str
    password_env: str


@dataclass
class RedisDraft:
    host: str
    port: int
    db: int
    password_env: str | None


@dataclass
class InfrastructureDraft:
    postgres: PostgresDraft
    redis: RedisDraft


@dataclass
class AgentDraft:
    provider: ProviderId
    model: str
    prompt_file: str


@dataclass
class ProviderPricingDraft:
    input_per_1k_tokens: Decimal | None
    output_per_1k_tokens: Decimal | None


@dataclass
class ProviderDraft:
    api_key_env: str
    rate_limit_per_minute: int | None
    pricing: ProviderPricingDraft | None


@dataclass
class CollectionScoringDraft:
    weight_score: float | None
    weight_comments: float | None
    weight_recency: float | None


@dataclass
class CollectionDraft:
    candidate_count: int
    scoring: CollectionScoringDraft | None


@dataclass
class WorkflowDraft:
    max_scenario_revisions: int


@dataclass
class WorkerDraft:
    topic_selector_concurrency: int
    scenario_generator_concurrency: int
    critic_concurrency: int


@dataclass
class BackoffDraft:
    initial_seconds: float
    multiplier: float
    max_seconds: float


@dataclass
class RetryPolicyDraft:
    max_attempts: int
    backoff: BackoffDraft


@dataclass
class TimeoutDraft:
    connect_seconds: float | None
    read_seconds: float
    total_seconds: float | None


@dataclass
class FailureInjectionDraft:
    enabled: bool
    active_injections: list[InjectionId | str]


@dataclass
class ConfigDraft:
    config_version: str | None
    infrastructure: InfrastructureDraft
    agents: dict[AgentId, AgentDraft]
    providers: dict[ProviderId, ProviderDraft]
    collection: CollectionDraft
    workflow: WorkflowDraft
    workers: WorkerDraft
    retry: dict[TaskType, RetryPolicyDraft]
    timeouts: dict[ProviderId, TimeoutDraft]
    failure_injection: FailureInjectionDraft
