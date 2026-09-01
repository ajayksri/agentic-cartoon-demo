"""Shared contract-test fixtures for providers module (PRV-018, LLD §7, §15.4)."""

from __future__ import annotations

import pytest

from config.types import AppConfig, ProviderId, ProviderPricing
from decimal import Decimal

from .helpers import (
    CredentialResolveSpy,
    minimal_provider_config,
    valid_generate_request,
)


@pytest.fixture
def minimal_provider_config_fixture() -> AppConfig:
    return minimal_provider_config()


@pytest.fixture
def openai_only_config_fixture() -> AppConfig:
    return minimal_provider_config(
        openai_only_agents=True,
        credential_resolver=CredentialResolveSpy(
            {"OPENAI_API_KEY": "openai-test-key"},
        ),
    )


@pytest.fixture
def valid_generate_request_fixture() -> object:
    return valid_generate_request


@pytest.fixture
def provider_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set credential env vars for all configured providers."""
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-test-key")


@pytest.fixture
def priced_openai_config(provider_env_keys: None) -> AppConfig:
    return minimal_provider_config(
        openai_pricing=ProviderPricing(
            input_per_1k_tokens=Decimal("0.01"),
            output_per_1k_tokens=Decimal("0.02"),
        ),
    )


@pytest.fixture
def short_timeout_config(provider_env_keys: None) -> AppConfig:
    return minimal_provider_config(openai_read_seconds=0.05)
