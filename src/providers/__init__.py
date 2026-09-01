"""Providers module public surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
    default_retryable,
)
from .protocols import FakeProvider, ModelProvider
from .types import (
    GenerateRequest,
    GenerateResponse,
    ProviderErrorClass,
    ProviderMessage,
    ProviderMessageRole,
    TokenUsage,
)

if TYPE_CHECKING:
    from config.types import AppConfig, ProviderId
    from failure_injection.protocols import FailureInjectionRegistry


from .factory import create_provider as _create_provider_impl


def create_provider(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    registry: FailureInjectionRegistry | None = None,
) -> ModelProvider:
    """Construct a provider adapter for the given provider ID."""
    return _create_provider_impl(
        provider_id=provider_id,
        config=config,
        registry=registry,
    )


__all__ = [
    "FakeProvider",
    "GenerateRequest",
    "GenerateResponse",
    "ModelProvider",
    "ProviderAuthenticationError",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderErrorClass",
    "ProviderMessage",
    "ProviderMessageRole",
    "ProviderNetworkError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderSchemaValidationError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "ProviderUnknownError",
    "TokenUsage",
    "create_provider",
    "default_retryable",
]


def __dir__() -> list[str]:
    return sorted(__all__)
