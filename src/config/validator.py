"""Config validation stages S3–S6: referential, numeric, prompt, credentials."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from config.credentials import InfraCredChecker, ProviderCredChecker
from config.draft import AgentDraft, ConfigDraft
from config.errors import ConfigPromptNotFoundError, ConfigValueError
from config.messages import prompt_message, validation_message
from config.types import AgentId, InjectionId


def _raise_value_error(*, key_path: str, reason: str, constraint: str) -> None:
    raise ConfigValueError(
        validation_message(key_path=key_path, reason=reason, constraint=constraint),
        key_path=key_path,
    )


class PromptChecker:
    def check_all(self, agents: Mapping[AgentId, AgentDraft]) -> None:
        for agent_id, agent in agents.items():
            key_path = f"agents.{agent_id.value}.prompt_file"
            prompt_path = Path(agent.prompt_file)
            if prompt_path.is_absolute() or not prompt_path.is_file():
                raise ConfigPromptNotFoundError(
                    prompt_message(key_path=key_path, prompt_file=agent.prompt_file),
                    prompt_file=agent.prompt_file,
                )


class ConfigValidator:
    def __init__(
        self,
        *,
        prompt_checker: PromptChecker | None = None,
        provider_cred_checker: ProviderCredChecker | None = None,
        infra_cred_checker: InfraCredChecker | None = None,
    ) -> None:
        self._prompt_checker = prompt_checker or PromptChecker()
        self._provider_cred_checker = provider_cred_checker or ProviderCredChecker()
        self._infra_cred_checker = infra_cred_checker or InfraCredChecker()

    def validate(self, draft: ConfigDraft) -> ConfigDraft:
        self._validate_referential_integrity(draft)
        self._validate_numeric_constraints(draft)
        self._prompt_checker.check_all(draft.agents)
        self._provider_cred_checker.check_referenced_providers(
            draft.agents, draft.providers
        )
        self._infra_cred_checker.check(draft.infrastructure)
        return draft

    def _validate_referential_integrity(self, draft: ConfigDraft) -> None:
        for agent_id, agent in draft.agents.items():
            if agent.provider not in draft.providers:
                key_path = f"agents.{agent_id.value}.provider"
                _raise_value_error(
                    key_path=key_path,
                    reason=f"Provider '{agent.provider.value}' is not defined in providers",
                    constraint="reference to a defined provider",
                )

        valid_injection_values = {member.value for member in InjectionId}
        for index, injection in enumerate(draft.failure_injection.active_injections):
            value = injection.value if isinstance(injection, InjectionId) else injection
            if value not in valid_injection_values:
                _raise_value_error(
                    key_path=f"failure_injection.active_injections[{index}]",
                    reason=f"Unknown injection ID '{value}'",
                    constraint="one of the defined InjectionId values",
                )

    def _validate_numeric_constraints(self, draft: ConfigDraft) -> None:
        if draft.collection.candidate_count <= 0:
            _raise_value_error(
                key_path="collection.candidate_count",
                reason=f"Value must be positive (got {draft.collection.candidate_count})",
                constraint="integer > 0",
            )

        if draft.workflow.max_scenario_revisions <= 0:
            _raise_value_error(
                key_path="workflow.max_scenario_revisions",
                reason=(
                    f"Value must be positive (got {draft.workflow.max_scenario_revisions})"
                ),
                constraint="integer > 0",
            )

        worker_fields = (
            ("topic_selector_concurrency", draft.workers.topic_selector_concurrency),
            ("scenario_generator_concurrency", draft.workers.scenario_generator_concurrency),
            ("critic_concurrency", draft.workers.critic_concurrency),
        )
        for field_name, value in worker_fields:
            if value <= 0:
                _raise_value_error(
                    key_path=f"workers.{field_name}",
                    reason=f"Value must be positive (got {value})",
                    constraint="integer > 0",
                )

        for task_type, policy in draft.retry.items():
            base = f"retry.{task_type.value}"
            if policy.max_attempts < 1:
                _raise_value_error(
                    key_path=f"{base}.max_attempts",
                    reason=f"Value must be at least 1 (got {policy.max_attempts})",
                    constraint="integer >= 1",
                )
            backoff_fields = (
                ("initial_seconds", policy.backoff.initial_seconds),
                ("multiplier", policy.backoff.multiplier),
                ("max_seconds", policy.backoff.max_seconds),
            )
            for field_name, value in backoff_fields:
                if value <= 0:
                    _raise_value_error(
                        key_path=f"{base}.backoff.{field_name}",
                        reason=f"Value must be positive (got {value})",
                        constraint="number > 0",
                    )

        for provider_id, timeout in draft.timeouts.items():
            base = f"timeouts.{provider_id.value}"
            if timeout.read_seconds <= 0:
                _raise_value_error(
                    key_path=f"{base}.read_seconds",
                    reason=f"Value must be positive (got {timeout.read_seconds})",
                    constraint="number > 0",
                )
            if timeout.connect_seconds is not None and timeout.connect_seconds <= 0:
                _raise_value_error(
                    key_path=f"{base}.connect_seconds",
                    reason=f"Value must be positive (got {timeout.connect_seconds})",
                    constraint="number > 0",
                )
            if timeout.total_seconds is not None and timeout.total_seconds <= 0:
                _raise_value_error(
                    key_path=f"{base}.total_seconds",
                    reason=f"Value must be positive (got {timeout.total_seconds})",
                    constraint="number > 0",
                )

        for provider_id, provider in draft.providers.items():
            if provider.rate_limit_per_minute is not None and provider.rate_limit_per_minute <= 0:
                _raise_value_error(
                    key_path=f"providers.{provider_id.value}.rate_limit_per_minute",
                    reason=(
                        f"Value must be positive (got {provider.rate_limit_per_minute})"
                    ),
                    constraint="integer > 0",
                )
