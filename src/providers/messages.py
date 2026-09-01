"""Error message templates for the providers module."""

from __future__ import annotations

from config.types import ProviderId

from .constants import VENDOR_DETAIL_MAX_LENGTH
from .types import ProviderErrorClass


def truncate_vendor_detail(detail: str | None) -> str:
    if detail is None:
        return ""
    return detail[:VENDOR_DETAIL_MAX_LENGTH]


def provider_error_message(
    *,
    code: str,
    error_class: ProviderErrorClass,
    provider_id: ProviderId,
    reason: str,
    retryable: bool,
) -> str:
    truncated = truncate_vendor_detail(reason)
    return (
        f"{code}: {error_class.value} provider={provider_id.value} — "
        f"{truncated} (retryable={retryable})"
    )


def configuration_error_message(*, provider_id: ProviderId, reason: str) -> str:
    return f"PRV_CONFIG: provider {provider_id.value} {reason}"


def client_rate_limit_message(*, provider_id: ProviderId) -> str:
    return provider_error_message(
        code="PRV_RATE",
        error_class=ProviderErrorClass.RATE_LIMIT,
        provider_id=provider_id,
        reason="client rate limit exceeded",
        retryable=True,
    )
