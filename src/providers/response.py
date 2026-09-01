"""GenerateResponse assembly."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from config.types import ProviderId

from .types import GenerateRequest, GenerateResponse, TokenUsage

if TYPE_CHECKING:
    pass


class _VendorResult(Protocol):
    content: str
    model: str
    token_usage: TokenUsage | None


class ResponseAssembler:
    def build_success(
        self,
        *,
        request: GenerateRequest,
        provider_id: ProviderId,
        vendor_result: _VendorResult,
        latency_ms: float,
        estimated_cost_usd: Decimal | None,
    ) -> GenerateResponse:
        return GenerateResponse(
            content=vendor_result.content,
            model=vendor_result.model,
            provider_id=provider_id,
            latency_ms=latency_ms,
            token_usage=vendor_result.token_usage,
            estimated_cost_usd=estimated_cost_usd,
        )
