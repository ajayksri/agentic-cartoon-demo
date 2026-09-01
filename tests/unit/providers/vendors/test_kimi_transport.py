"""Pre-code test mold for Kimi transport — OpenAI-compatible Moonshot API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from providers import GenerateRequest, ProviderMessage, ProviderMessageRole, TokenUsage


def _request() -> GenerateRequest:
    return GenerateRequest(
        model="moonshot-v1-8k",
        messages=(
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content="system"),
            ProviderMessage(role=ProviderMessageRole.USER, content="hello"),
        ),
    )


def _budget(*, read_seconds: float = 30.0) -> object:
    from providers.timeout import TimeoutBudget

    return TimeoutBudget(
        connect_seconds=None,
        read_seconds=read_seconds,
        total_seconds=None,
        overall_deadline_seconds=read_seconds,
    )


def _transport_with_client(mock_client: MagicMock) -> object:
    from providers.vendors.kimi import KimiTransport

    return KimiTransport(api_key="test-key", client=mock_client)


def test_transport_uses_moonshot_base_url() -> None:
    """KimiTransport targets the Moonshot OpenAI-compatible endpoint."""
    from providers.vendors.kimi import MOONSHOT_API_BASE_URL, KimiTransport

    with patch("providers.vendors.kimi.OpenAI") as openai_cls:
        KimiTransport(api_key="test-key")

    openai_cls.assert_called_once_with(
        api_key="test-key",
        base_url=MOONSHOT_API_BASE_URL,
    )


def test_complete_success_maps_vendor_call_result() -> None:
    """Successful SDK response maps to VendorCallResult with token usage."""
    from providers.vendors._transport import VendorCallResult

    mock_client = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content="assistant reply"))]
    completion.model = "moonshot-v1-8k"
    completion.usage = MagicMock(prompt_tokens=12, completion_tokens=7)
    mock_client.with_options.return_value.chat.completions.create.return_value = completion

    transport = _transport_with_client(mock_client)
    result = transport.complete(_request(), timeout=_budget())

    assert isinstance(result, VendorCallResult)
    assert result.content == "assistant reply"
    assert result.model == "moonshot-v1-8k"
    assert result.token_usage == TokenUsage(input_tokens=12, output_tokens=7)


def test_rate_limit_error_raises_vendor_transport_error() -> None:
    """openai.RateLimitError maps to rate-limit VendorFailureSignal."""
    import openai

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.chat.completions.create.side_effect = (
        openai.RateLimitError("rate limited", response=MagicMock(status_code=429), body=None)
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_rate_limit is True
