"""Internal vendor transport value types shared across provider internals."""

from __future__ import annotations

from dataclasses import dataclass

from config.types import ProviderId

from .types import TokenUsage


@dataclass(frozen=True, slots=True)
class VendorCallResult:
    content: str
    model: str
    token_usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class VendorFailureSignal:
    http_status: int | None = None
    vendor_code: str | None = None
    vendor_message: str | None = None
    exception_type: str | None = None
    is_timeout: bool = False
    is_connection_error: bool = False
    is_rate_limit: bool = False
    is_auth_error: bool = False
    is_schema_validation: bool = False
    is_service_unavailable: bool = False
    provider_id: ProviderId | None = None


class VendorTransportError(Exception):
    def __init__(self, signal: VendorFailureSignal) -> None:
        self.signal = signal
        super().__init__("vendor transport failure")
