"""Public configuration value types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class AgentId(StrEnum):
    TOPIC_SELECTOR = "topic_selector"
    SCENARIO_GENERATOR = "scenario_generator"
    CRITIC = "critic"


class ProviderId(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    KIMI = "kimi"
    FAKE = "fake"


class TaskType(StrEnum):
    COLLECT = "COLLECT"
    SELECT_TOPIC = "SELECT_TOPIC"
    GENERATE_SCENARIO = "GENERATE_SCENARIO"
    REVIEW_SCENARIO = "REVIEW_SCENARIO"


class InjectionId(StrEnum):
    FINJ_WKR_PRE = "FINJ-WKR-PRE"
    FINJ_WKR_POST_AGENT = "FINJ-WKR-POST-AGENT"
    FINJ_WKR_POST_COMMIT = "FINJ-WKR-POST-COMMIT"
    FINJ_WKR_PRE_ACK = "FINJ-WKR-PRE-ACK"
    FINJ_Q_DUP = "FINJ-Q-DUP"
    FINJ_Q_SLOW = "FINJ-Q-SLOW"
    FINJ_PRV_TIMEOUT = "FINJ-PRV-TIMEOUT"
    FINJ_PRV_RATE = "FINJ-PRV-RATE"
    FINJ_PRV_ERROR = "FINJ-PRV-ERROR"
    FINJ_PRV_INVALID = "FINJ-PRV-INVALID"
    FINJ_COORD_DISPATCH = "FINJ-COORD-DISPATCH"
    FINJ_COORD_CONFLICT = "FINJ-COORD-CONFLICT"


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """Env var name holding a secret; never the secret value."""

    env_var_name: str


@dataclass(frozen=True, slots=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user_env: str
    password_env: str


@dataclass(frozen=True, slots=True)
class RedisConfig:
    host: str
    port: int
    db: int
    password_env: str | None


@dataclass(frozen=True, slots=True)
class InfrastructureConfig:
    postgres: PostgresConfig
    redis: RedisConfig


@dataclass(frozen=True, slots=True)
class AgentConfig:
    provider: ProviderId
    model: str
    prompt_file: str


@dataclass(frozen=True, slots=True)
class ProviderPricing:
    input_per_1k_tokens: Decimal | None
    output_per_1k_tokens: Decimal | None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    api_key_env: str
    rate_limit_per_minute: int | None
    pricing: ProviderPricing | None


@dataclass(frozen=True, slots=True)
class CollectionScoringConfig:
    """Deterministic scoring parameters for story reduction."""

    weight_score: float | None
    weight_comments: float | None
    weight_recency: float | None


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    candidate_count: int
    scoring: CollectionScoringConfig | None


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    max_scenario_revisions: int


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    topic_selector_concurrency: int
    scenario_generator_concurrency: int
    critic_concurrency: int


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    initial_seconds: float
    multiplier: float
    max_seconds: float


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    backoff: BackoffConfig


@dataclass(frozen=True, slots=True)
class TimeoutConfig:
    connect_seconds: float | None
    read_seconds: float
    total_seconds: float | None


@dataclass(frozen=True, slots=True)
class FailureInjectionConfig:
    enabled: bool
    active_injections: frozenset[InjectionId]


@dataclass(frozen=True, slots=True)
class ConfigSource:
    """Identifies where to load configuration from."""

    path: Path | None = None


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated, immutable application configuration."""

    infrastructure: InfrastructureConfig
    agents: Mapping[AgentId, AgentConfig]
    providers: Mapping[ProviderId, ProviderConfig]
    collection: CollectionConfig
    workflow: WorkflowConfig
    workers: WorkerConfig
    retry: Mapping[TaskType, RetryPolicy]
    timeouts: Mapping[ProviderId, TimeoutConfig]
    failure_injection: FailureInjectionConfig

    def get_agent_config(self, agent_id: AgentId) -> AgentConfig:
        raise NotImplementedError

    def get_provider_config(self, provider_id: ProviderId) -> ProviderConfig:
        raise NotImplementedError

    def get_retry_policy(self, task_type: TaskType) -> RetryPolicy:
        raise NotImplementedError

    def get_worker_concurrency(self, agent_id: AgentId) -> int:
        raise NotImplementedError

    def resolve_credential(self, env_var_name: str) -> str:
        raise NotImplementedError

    def is_injection_active(self, injection_id: InjectionId) -> bool:
        raise NotImplementedError
