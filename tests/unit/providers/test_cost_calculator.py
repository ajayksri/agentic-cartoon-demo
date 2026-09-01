"""Pre-code test mold for PRV-005 — CostCalculator (LLD §4.8, CG-PRV-006)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from config.types import ProviderPricing
from providers.types import TokenUsage

@pytest.mark.prv_tc("044")
def test_estimate_with_pricing_returns_quantized_decimal() -> None:
    """PRV-TC-044: pricing + token counts → six-decimal USD estimate."""
    from providers.cost import CostCalculator

    pricing = ProviderPricing(
        input_per_1k_tokens=Decimal("0.003000"),
        output_per_1k_tokens=Decimal("0.015000"),
    )
    usage = TokenUsage(input_tokens=1000, output_tokens=500, cached_tokens=200)
    calculator = CostCalculator(pricing=pricing)

    estimate = calculator.estimate(usage)

    assert estimate == Decimal("0.010500")
@pytest.mark.prv_tc("045")
def test_estimate_without_pricing_returns_none() -> None:
    """PRV-TC-045: missing pricing config → None cost."""
    from providers.cost import CostCalculator

    usage = TokenUsage(input_tokens=100, output_tokens=50)
    calculator = CostCalculator(pricing=None)

    assert calculator.estimate(usage) is None
def test_estimate_returns_none_when_token_usage_incomplete() -> None:
    """None input or output tokens → None (CG-PRV-006)."""
    from providers.cost import CostCalculator

    pricing = ProviderPricing(
        input_per_1k_tokens=Decimal("0.001"),
        output_per_1k_tokens=Decimal("0.002"),
    )
    calculator = CostCalculator(pricing=pricing)

    assert calculator.estimate(None) is None
    assert calculator.estimate(TokenUsage(input_tokens=None, output_tokens=10)) is None
    assert calculator.estimate(TokenUsage(input_tokens=10, output_tokens=None)) is None
def test_cached_tokens_excluded_from_cost() -> None:
    """V1: cached_tokens recorded but excluded from cost formula."""
    from providers.cost import CostCalculator

    pricing = ProviderPricing(
        input_per_1k_tokens=Decimal("0.010000"),
        output_per_1k_tokens=Decimal("0.000000"),
    )
    without_cached = TokenUsage(input_tokens=1000, output_tokens=0, cached_tokens=None)
    with_cached = TokenUsage(input_tokens=1000, output_tokens=0, cached_tokens=900)
    calculator = CostCalculator(pricing=pricing)

    assert calculator.estimate(without_cached) == calculator.estimate(with_cached)
def test_estimate_rounds_half_up_to_six_decimals() -> None:
    """Result quantized to 0.000001 with ROUND_HALF_UP."""
    from providers.cost import CostCalculator

    pricing = ProviderPricing(
        input_per_1k_tokens=Decimal("0.000333"),
        output_per_1k_tokens=Decimal("0.000000"),
    )
    usage = TokenUsage(input_tokens=1, output_tokens=0)
    calculator = CostCalculator(pricing=pricing)

    estimate = calculator.estimate(usage)

    assert estimate == Decimal("0.000000")
