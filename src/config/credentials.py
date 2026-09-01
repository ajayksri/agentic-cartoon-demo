"""Credential checkers and resolver for validation stage S6."""

from __future__ import annotations

import os
from collections.abc import Mapping

from config.draft import AgentDraft, InfrastructureDraft, ProviderDraft
from config.errors import ConfigCredentialMissingError
from config.messages import credential_message
from config.types import AgentId, ProviderId


def _require_env(env_var_name: str) -> str:
    if os.environ.get(env_var_name, "") == "":
        raise ConfigCredentialMissingError(
            credential_message(env_var_name=env_var_name),
            env_var_name=env_var_name,
        )
    return os.environ[env_var_name]


class ProviderCredChecker:
    def check_referenced_providers(
        self,
        agents: Mapping[AgentId, AgentDraft],
        providers: Mapping[ProviderId, ProviderDraft],
    ) -> None:
        referenced = {agent.provider for agent in agents.values()}
        for provider_id in referenced:
            _require_env(providers[provider_id].api_key_env)


class InfraCredChecker:
    def check(self, infrastructure: InfrastructureDraft) -> None:
        postgres = infrastructure.postgres
        _require_env(postgres.user_env)
        _require_env(postgres.password_env)
        if infrastructure.redis.password_env is not None:
            _require_env(infrastructure.redis.password_env)


class CredentialResolver:
    def resolve(self, env_var_name: str) -> str:
        return _require_env(env_var_name)
