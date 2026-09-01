"""Token cost estimation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from config.types import ProviderPricing

from .types import TokenUsage


class CostCalculator:
    def __init__(self, *, pricing: ProviderPricing | None) -> None:
        self._pricing = pricing

    def estimate(self, token_usage: TokenUsage | None) -> Decimal | None:
        if self._pricing is None or token_usage is None:
            return None
        if token_usage.input_tokens is None or token_usage.output_tokens is None:
            return None

        input_rate = self._pricing.input_per_1k_tokens
        output_rate = self._pricing.output_per_1k_tokens
        if input_rate is None or output_rate is None:
            return None

        raw = (Decimal(token_usage.input_tokens) / Decimal(1000)) * input_rate + (
            Decimal(token_usage.output_tokens) / Decimal(1000)
        ) * output_rate
        return raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
