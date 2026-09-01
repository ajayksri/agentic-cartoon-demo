"""Public provider error types."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ProviderErrorClass

if TYPE_CHECKING:
    from config.types import ProviderId


class ProviderError(Exception):
    """Base class for all provider module errors."""

    code: str = "PRV_ERROR"
    error_class: ProviderErrorClass = ProviderErrorClass.UNKNOWN
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider_id: ProviderId | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_id = provider_id


class ProviderTimeoutError(ProviderError):
    """Remote call exceeded configured deadline."""

    code = "PRV_TIMEOUT"
    error_class = ProviderErrorClass.TIMEOUT
    retryable = True


class ProviderRateLimitError(ProviderError):
    """Client or server rate limit exceeded."""

    code = "PRV_RATE"
    error_class = ProviderErrorClass.RATE_LIMIT
    retryable = True


class ProviderAuthenticationError(ProviderError):
    """Invalid or missing provider credentials."""

    code = "PRV_AUTH"
    error_class = ProviderErrorClass.AUTHENTICATION
    retryable = False


class ProviderUnavailableError(ProviderError):
    """Provider service temporarily unavailable."""

    code = "PRV_UNAVAILABLE"
    error_class = ProviderErrorClass.PROVIDER_UNAVAILABLE
    retryable = True


class ProviderResponseError(ProviderError):
    """Provider returned an unrecoverable error response."""

    code = "PRV_ERROR"
    error_class = ProviderErrorClass.PROVIDER_ERROR
    retryable = False


class ProviderNetworkError(ProviderError):
    """Network-level failure reaching the provider."""

    code = "PRV_NETWORK"
    error_class = ProviderErrorClass.NETWORK_ERROR
    retryable = True


class ProviderSchemaValidationError(ProviderError):
    """Structured provider output failed validation."""

    code = "PRV_SCHEMA"
    error_class = ProviderErrorClass.SCHEMA_VALIDATION
    retryable = False


class ProviderUnknownError(ProviderError):
    """Unmapped provider failure."""

    code = "PRV_UNKNOWN"
    error_class = ProviderErrorClass.UNKNOWN
    retryable = False


class ProviderConfigurationError(ProviderError):
    """Factory or adapter wiring failure."""

    code = "PRV_CONFIG"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider_id: ProviderId | None = None,
    ) -> None:
        super().__init__(message, provider_id=provider_id)


_DEFAULT_RETRYABLE: dict[ProviderErrorClass, bool] = {
    ProviderErrorClass.TIMEOUT: True,
    ProviderErrorClass.RATE_LIMIT: True,
    ProviderErrorClass.AUTHENTICATION: False,
    ProviderErrorClass.PROVIDER_UNAVAILABLE: True,
    ProviderErrorClass.PROVIDER_ERROR: False,
    ProviderErrorClass.NETWORK_ERROR: True,
    ProviderErrorClass.SCHEMA_VALIDATION: False,
    ProviderErrorClass.UNKNOWN: False,
}


def default_retryable(error_class: ProviderErrorClass) -> bool:
    """Return the module-default retryable flag for an error class."""
    return _DEFAULT_RETRYABLE[error_class]
