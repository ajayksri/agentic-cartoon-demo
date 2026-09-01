"""Pre-code test mold for PRV-004 — RequestValidator (LLD §4.3, PRV-TC-005)."""

from __future__ import annotations

import pytest

from providers.types import GenerateRequest, ProviderMessage, ProviderMessageRole

def _valid_request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-4o-mini",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hi"),),
    )
@pytest.mark.prv_tc("005")
def test_empty_messages_raises_value_error() -> None:
    """PRV-TC-005: empty messages list raises ValueError, not ProviderError."""
    from providers.validation import RequestValidator

    request = GenerateRequest(model="gpt-4o-mini", messages=())

    with pytest.raises(ValueError, match="messages must not be empty"):
        RequestValidator().validate(request)
@pytest.mark.prv_tc("005")
def test_blank_model_raises_value_error() -> None:
    """PRV-TC-005: whitespace-only model raises ValueError."""
    from providers.validation import RequestValidator

    request = GenerateRequest(
        model="   ",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hi"),),
    )

    with pytest.raises(ValueError, match="model must not be empty"):
        RequestValidator().validate(request)
def test_valid_minimal_request_passes_without_side_effects() -> None:
    """Valid request passes validation with no mutation."""
    from providers.validation import RequestValidator

    request = _valid_request()
    RequestValidator().validate(request)
    assert request.model == "gpt-4o-mini"
