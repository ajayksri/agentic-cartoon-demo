"""Schema mapping from raw YAML tree to ConfigDraft."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
    RawConfigTree,
    RedisDraft,
    RetryPolicyDraft,
    TimeoutDraft,
    WorkerDraft,
    WorkflowDraft,
)
from config.errors import ConfigFormatError, ConfigMissingError
from config.messages import validation_message
from config.types import AgentId, InjectionId, ProviderId, TaskType


class SchemaMapper:
    SUPPORTED_CONFIG_VERSIONS: frozenset[str] = frozenset({"1"})

    def map(self, tree: RawConfigTree) -> ConfigDraft:
        """Map raw YAML dict to ConfigDraft."""
        config_version = self._map_config_version(tree)

        infrastructure = self._map_infrastructure(
            self._require_domain(tree, "infrastructure")
        )
        agents = self._map_agents(self._require_domain(tree, "agents"))
        providers = self._map_providers(self._require_domain(tree, "providers"))
        collection = self._map_collection(self._require_domain(tree, "collection"))
        workflow = self._map_workflow(self._require_domain(tree, "workflow"))
        workers = self._map_workers(self._require_domain(tree, "workers"))
        retry = self._map_retry(self._require_domain(tree, "retry"))
        timeouts = self._map_timeouts(
            self._require_domain(tree, "timeouts"),
            agents,
        )
        failure_injection = self._map_failure_injection(tree.get("failure_injection"))

        return ConfigDraft(
            config_version=config_version,
            infrastructure=infrastructure,
            agents=agents,
            providers=providers,
            collection=collection,
            workflow=workflow,
            workers=workers,
            retry=retry,
            timeouts=timeouts,
            failure_injection=failure_injection,
        )

    def _map_config_version(self, tree: RawConfigTree) -> str | None:
        if "config_version" not in tree:
            return None
        version = self._require_str(tree["config_version"], "config_version")
        if version not in self.SUPPORTED_CONFIG_VERSIONS:
            raise ConfigFormatError(
                validation_message(
                    key_path="config_version",
                    reason=f"Unsupported config version '{version}'",
                    constraint=f"one of {sorted(self.SUPPORTED_CONFIG_VERSIONS)}",
                ),
                key_path="config_version",
            )
        return version

    def _require_domain(self, tree: RawConfigTree, name: str) -> RawConfigTree:
        if name not in tree:
            raise ConfigMissingError(
                validation_message(
                    key_path=name,
                    reason="Required domain is missing",
                    constraint="present top-level mapping",
                ),
                key_path=name,
            )
        return self._require_mapping(tree[name], name)

    def _require_key(self, mapping: RawConfigTree, key: str, key_path: str) -> object:
        if key not in mapping:
            raise ConfigMissingError(
                validation_message(
                    key_path=key_path,
                    reason="Required key is missing",
                    constraint="present key",
                ),
                key_path=key_path,
            )
        return mapping[key]

    def _require_mapping(self, node: object, key_path: str) -> RawConfigTree:
        if not isinstance(node, dict):
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason="Value is not a mapping",
                    constraint="object mapping",
                ),
                key_path=key_path,
            )
        return node

    def _require_str(self, node: object, key_path: str) -> str:
        if not isinstance(node, str):
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason=f"Value has wrong type ({type(node).__name__})",
                    constraint="non-empty string",
                ),
                key_path=key_path,
            )
        stripped = node.strip()
        if not stripped:
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason="String is empty or whitespace-only",
                    constraint="non-empty string",
                ),
                key_path=key_path,
            )
        return stripped

    def _require_int(self, node: object, key_path: str) -> int:
        if isinstance(node, bool) or not isinstance(node, int):
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason=f"Value has wrong type ({type(node).__name__})",
                    constraint="integer",
                ),
                key_path=key_path,
            )
        return node

    def _require_positive_float(self, node: object, key_path: str) -> float:
        if isinstance(node, bool):
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason=f"Value has wrong type ({type(node).__name__})",
                    constraint="number",
                ),
                key_path=key_path,
            )
        if isinstance(node, int):
            return float(node)
        if isinstance(node, float):
            return node
        raise ConfigFormatError(
            validation_message(
                key_path=key_path,
                reason=f"Value has wrong type ({type(node).__name__})",
                constraint="number",
            ),
            key_path=key_path,
        )

    def _optional_float(self, node: object | None, key_path: str) -> float | None:
        if node is None:
            return None
        return self._require_positive_float(node, key_path)

    def _optional_decimal(self, node: object | None, key_path: str) -> Decimal | None:
        if node is None:
            return None
        if isinstance(node, Decimal):
            return node
        if isinstance(node, bool):
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason=f"Value has wrong type ({type(node).__name__})",
                    constraint="decimal number or null",
                ),
                key_path=key_path,
            )
        if isinstance(node, int):
            return Decimal(node)
        if isinstance(node, float):
            return Decimal(str(node))
        if isinstance(node, str):
            try:
                return Decimal(node)
            except InvalidOperation as exc:
                raise ConfigFormatError(
                    validation_message(
                        key_path=key_path,
                        reason="Value is not a valid decimal",
                        constraint="decimal number or null",
                    ),
                    key_path=key_path,
                ) from exc
        raise ConfigFormatError(
            validation_message(
                key_path=key_path,
                reason=f"Value has wrong type ({type(node).__name__})",
                constraint="decimal number or null",
            ),
            key_path=key_path,
        )

    def _parse_provider_id(self, value: object, key_path: str) -> ProviderId:
        provider_str = self._require_str(value, key_path)
        try:
            return ProviderId(provider_str)
        except ValueError as exc:
            raise ConfigFormatError(
                validation_message(
                    key_path=key_path,
                    reason=f"Invalid provider id '{provider_str}'",
                    constraint=f"one of {[p.value for p in ProviderId]}",
                ),
                key_path=key_path,
            ) from exc

    def _reject_unknown_keys(
        self,
        node: RawConfigTree,
        *,
        prefix: str,
        allowed: set[str],
    ) -> None:
        for key in node:
            if key not in allowed:
                raise ConfigFormatError(
                    validation_message(
                        key_path=f"{prefix}.{key}",
                        reason=f"Unknown key '{key}'",
                        constraint=f"whitelist keys: {sorted(allowed)}",
                    ),
                    key_path=f"{prefix}.{key}",
                )

    def _map_infrastructure(self, node: RawConfigTree) -> InfrastructureDraft:
        postgres_node = self._require_mapping(
            self._require_key(node, "postgres", "infrastructure.postgres"),
            "infrastructure.postgres",
        )
        redis_node = self._require_mapping(
            self._require_key(node, "redis", "infrastructure.redis"),
            "infrastructure.redis",
        )

        postgres = PostgresDraft(
            host=self._require_str(
                self._require_key(postgres_node, "host", "infrastructure.postgres.host"),
                "infrastructure.postgres.host",
            ),
            port=self._require_int(
                self._require_key(postgres_node, "port", "infrastructure.postgres.port"),
                "infrastructure.postgres.port",
            ),
            database=self._require_str(
                self._require_key(
                    postgres_node, "database", "infrastructure.postgres.database"
                ),
                "infrastructure.postgres.database",
            ),
            user_env=self._require_str(
                self._require_key(
                    postgres_node, "user_env", "infrastructure.postgres.user_env"
                ),
                "infrastructure.postgres.user_env",
            ),
            password_env=self._require_str(
                self._require_key(
                    postgres_node, "password_env", "infrastructure.postgres.password_env"
                ),
                "infrastructure.postgres.password_env",
            ),
        )

        redis_password_env: str | None = None
        if "password_env" in redis_node:
            redis_password_env = self._require_str(
                redis_node["password_env"],
                "infrastructure.redis.password_env",
            )

        redis = RedisDraft(
            host=self._require_str(
                self._require_key(redis_node, "host", "infrastructure.redis.host"),
                "infrastructure.redis.host",
            ),
            port=self._require_int(
                self._require_key(redis_node, "port", "infrastructure.redis.port"),
                "infrastructure.redis.port",
            ),
            db=self._require_int(
                self._require_key(redis_node, "db", "infrastructure.redis.db"),
                "infrastructure.redis.db",
            ),
            password_env=redis_password_env,
        )

        return InfrastructureDraft(postgres=postgres, redis=redis)

    def _map_agents(self, node: RawConfigTree) -> dict[AgentId, AgentDraft]:
        allowed = {agent_id.value for agent_id in AgentId}
        self._reject_unknown_keys(node, prefix="agents", allowed=allowed)

        agents: dict[AgentId, AgentDraft] = {}
        for agent_id in AgentId:
            key_path = f"agents.{agent_id.value}"
            if agent_id.value not in node:
                raise ConfigMissingError(
                    validation_message(
                        key_path=key_path,
                        reason="Required agent configuration is missing",
                        constraint="present agent mapping",
                    ),
                    key_path=key_path,
                )
            agent_node = self._require_mapping(node[agent_id.value], key_path)
            agents[agent_id] = AgentDraft(
                provider=self._parse_provider_id(
                    self._require_key(agent_node, "provider", f"{key_path}.provider"),
                    f"{key_path}.provider",
                ),
                model=self._require_str(
                    self._require_key(agent_node, "model", f"{key_path}.model"),
                    f"{key_path}.model",
                ),
                prompt_file=self._require_str(
                    self._require_key(agent_node, "prompt_file", f"{key_path}.prompt_file"),
                    f"{key_path}.prompt_file",
                ),
            )
        return agents

    def _map_providers(self, node: RawConfigTree) -> dict[ProviderId, ProviderDraft]:
        allowed = {provider_id.value for provider_id in ProviderId}
        self._reject_unknown_keys(node, prefix="providers", allowed=allowed)

        providers: dict[ProviderId, ProviderDraft] = {}
        for provider_key, provider_node in node.items():
            provider_id = ProviderId(provider_key)
            key_path = f"providers.{provider_key}"
            mapping = self._require_mapping(provider_node, key_path)

            pricing: ProviderPricingDraft | None = None
            if "pricing" in mapping:
                pricing_node = self._require_mapping(
                    mapping["pricing"],
                    f"{key_path}.pricing",
                )
                pricing = ProviderPricingDraft(
                    input_per_1k_tokens=self._optional_decimal(
                        pricing_node.get("input_per_1k_tokens"),
                        f"{key_path}.pricing.input_per_1k_tokens",
                    ),
                    output_per_1k_tokens=self._optional_decimal(
                        pricing_node.get("output_per_1k_tokens"),
                        f"{key_path}.pricing.output_per_1k_tokens",
                    ),
                )

            rate_limit: int | None = None
            if "rate_limit_per_minute" in mapping:
                rate_limit = self._require_int(
                    mapping["rate_limit_per_minute"],
                    f"{key_path}.rate_limit_per_minute",
                )

            providers[provider_id] = ProviderDraft(
                api_key_env=self._require_str(
                    self._require_key(mapping, "api_key_env", f"{key_path}.api_key_env"),
                    f"{key_path}.api_key_env",
                ),
                rate_limit_per_minute=rate_limit,
                pricing=pricing,
            )
        return providers

    def _map_collection(self, node: RawConfigTree) -> CollectionDraft:
        scoring: CollectionScoringDraft | None = None
        if "scoring" in node:
            scoring_node = self._require_mapping(node["scoring"], "collection.scoring")
            scoring = self._map_collection_scoring(scoring_node)

        return CollectionDraft(
            candidate_count=self._require_int(
                self._require_key(node, "candidate_count", "collection.candidate_count"),
                "collection.candidate_count",
            ),
            scoring=scoring,
        )

    def _map_collection_scoring(self, node: RawConfigTree) -> CollectionScoringDraft:
        weights = ("weight_score", "weight_comments", "weight_recency")
        values: dict[str, float | None] = {}
        for weight in weights:
            key_path = f"collection.scoring.{weight}"
            if weight not in node:
                raise ConfigMissingError(
                    validation_message(
                        key_path=key_path,
                        reason="Required scoring weight is missing",
                        constraint="present weight key when scoring block is present",
                    ),
                    key_path=key_path,
                )
            values[weight] = self._optional_float(node[weight], key_path)
        return CollectionScoringDraft(
            weight_score=values["weight_score"],
            weight_comments=values["weight_comments"],
            weight_recency=values["weight_recency"],
        )

    def _map_workflow(self, node: RawConfigTree) -> WorkflowDraft:
        return WorkflowDraft(
            max_scenario_revisions=self._require_int(
                self._require_key(
                    node, "max_scenario_revisions", "workflow.max_scenario_revisions"
                ),
                "workflow.max_scenario_revisions",
            ),
        )

    def _map_workers(self, node: RawConfigTree) -> WorkerDraft:
        return WorkerDraft(
            topic_selector_concurrency=self._require_int(
                self._require_key(
                    node,
                    "topic_selector_concurrency",
                    "workers.topic_selector_concurrency",
                ),
                "workers.topic_selector_concurrency",
            ),
            scenario_generator_concurrency=self._require_int(
                self._require_key(
                    node,
                    "scenario_generator_concurrency",
                    "workers.scenario_generator_concurrency",
                ),
                "workers.scenario_generator_concurrency",
            ),
            critic_concurrency=self._require_int(
                self._require_key(
                    node, "critic_concurrency", "workers.critic_concurrency"
                ),
                "workers.critic_concurrency",
            ),
        )

    def _map_retry(self, node: RawConfigTree) -> dict[TaskType, RetryPolicyDraft]:
        allowed = {task_type.value for task_type in TaskType}
        self._reject_unknown_keys(node, prefix="retry", allowed=allowed)

        retry: dict[TaskType, RetryPolicyDraft] = {}
        for task_type in TaskType:
            key_path = f"retry.{task_type.value}"
            if task_type.value not in node:
                raise ConfigMissingError(
                    validation_message(
                        key_path=key_path,
                        reason="Required retry policy is missing",
                        constraint="present retry mapping",
                    ),
                    key_path=key_path,
                )
            retry[task_type] = self._map_retry_policy(
                self._require_mapping(node[task_type.value], key_path),
                key_path,
            )
        return retry

    def _map_retry_policy(self, node: RawConfigTree, key_path: str) -> RetryPolicyDraft:
        backoff_node = self._require_mapping(
            self._require_key(node, "backoff", f"{key_path}.backoff"),
            f"{key_path}.backoff",
        )
        return RetryPolicyDraft(
            max_attempts=self._require_int(
                self._require_key(node, "max_attempts", f"{key_path}.max_attempts"),
                f"{key_path}.max_attempts",
            ),
            backoff=BackoffDraft(
                initial_seconds=self._require_positive_float(
                    self._require_key(
                        backoff_node,
                        "initial_seconds",
                        f"{key_path}.backoff.initial_seconds",
                    ),
                    f"{key_path}.backoff.initial_seconds",
                ),
                multiplier=self._require_positive_float(
                    self._require_key(
                        backoff_node,
                        "multiplier",
                        f"{key_path}.backoff.multiplier",
                    ),
                    f"{key_path}.backoff.multiplier",
                ),
                max_seconds=self._require_positive_float(
                    self._require_key(
                        backoff_node,
                        "max_seconds",
                        f"{key_path}.backoff.max_seconds",
                    ),
                    f"{key_path}.backoff.max_seconds",
                ),
            ),
        )

    def _map_timeouts(
        self,
        node: RawConfigTree,
        agents: dict[AgentId, AgentDraft],
    ) -> dict[ProviderId, TimeoutDraft]:
        allowed = {provider_id.value for provider_id in ProviderId}
        self._reject_unknown_keys(node, prefix="timeouts", allowed=allowed)

        referenced = {agent.provider for agent in agents.values()}
        for provider_id in referenced:
            key_path = f"timeouts.{provider_id.value}"
            if provider_id.value not in node:
                raise ConfigMissingError(
                    validation_message(
                        key_path=key_path,
                        reason="Required timeout configuration is missing for referenced provider",
                        constraint="present timeout mapping",
                    ),
                    key_path=key_path,
                )

        timeouts: dict[ProviderId, TimeoutDraft] = {}
        for provider_key, timeout_node in node.items():
            provider_id = ProviderId(provider_key)
            key_path = f"timeouts.{provider_key}"
            mapping = self._require_mapping(timeout_node, key_path)
            timeouts[provider_id] = TimeoutDraft(
                connect_seconds=self._optional_float(
                    mapping.get("connect_seconds"),
                    f"{key_path}.connect_seconds",
                ),
                read_seconds=self._require_positive_float(
                    self._require_key(mapping, "read_seconds", f"{key_path}.read_seconds"),
                    f"{key_path}.read_seconds",
                ),
                total_seconds=self._optional_float(
                    mapping.get("total_seconds"),
                    f"{key_path}.total_seconds",
                ),
            )
        return timeouts

    def _map_failure_injection(
        self,
        node: RawConfigTree | object | None,
    ) -> FailureInjectionDraft:
        if node is None:
            return FailureInjectionDraft(enabled=False, active_injections=[])

        mapping = self._require_mapping(node, "failure_injection")
        enabled = bool(mapping.get("enabled", False))

        active_injections: list[InjectionId | str] = []
        if "active_injections" in mapping:
            injections_node = mapping["active_injections"]
            if not isinstance(injections_node, list):
                raise ConfigFormatError(
                    validation_message(
                        key_path="failure_injection.active_injections",
                        reason=f"Value has wrong type ({type(injections_node).__name__})",
                        constraint="list of injection ids",
                    ),
                    key_path="failure_injection.active_injections",
                )
            for index, item in enumerate(injections_node):
                key_path = f"failure_injection.active_injections[{index}]"
                injection_str = self._require_str(item, key_path)
                try:
                    active_injections.append(InjectionId(injection_str))
                except ValueError:
                    # Unknown IDs are validated at S3 (ConfigValueError), not S2.
                    active_injections.append(injection_str)

        return FailureInjectionDraft(
            enabled=enabled,
            active_injections=active_injections,
        )
