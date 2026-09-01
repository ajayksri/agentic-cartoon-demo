"""Public provider value types."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.types import ProviderId


class ProviderErrorClass(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    NETWORK_ERROR = "network_error"
    SCHEMA_VALIDATION = "schema_validation"
    UNKNOWN = "unknown"


class ProviderMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    role: ProviderMessageRole
    content: str


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    """Provider-agnostic completion request."""

    model: str
    messages: tuple[ProviderMessage, ...]
    temperature: float | None = None
    max_output_tokens: int | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    task_attempt: int | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class GenerateResponse:
    """Successful provider completion."""

    content: str
    model: str
    provider_id: ProviderId
    latency_ms: float
    token_usage: TokenUsage | None = None
    estimated_cost_usd: Decimal | None = None
