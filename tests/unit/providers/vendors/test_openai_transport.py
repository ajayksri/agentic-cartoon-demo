"""Pre-code test mold for PRV-015 — OpenAITransport (LLD §4.13, §6.1, §9.3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from providers import GenerateRequest, ProviderMessage, ProviderMessageRole, TokenUsage

def _request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-4",
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
    from providers.vendors.openai import OpenAITransport

    return OpenAITransport(api_key="test-key", client=mock_client)
def test_complete_success_maps_vendor_call_result() -> None:
    """Successful SDK response maps to VendorCallResult with token usage."""
    from providers.vendors._transport import VendorCallResult

    mock_client = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content="assistant reply"))]
    completion.model = "gpt-4"
    completion.usage = MagicMock(prompt_tokens=12, completion_tokens=7)
    mock_client.with_options.return_value.chat.completions.create.return_value = completion

    transport = _transport_with_client(mock_client)
    result = transport.complete(_request(), timeout=_budget())

    assert isinstance(result, VendorCallResult)
    assert result.content == "assistant reply"
    assert result.model == "gpt-4"
    assert result.token_usage == TokenUsage(input_tokens=12, output_tokens=7)
def test_api_timeout_error_raises_vendor_transport_error() -> None:
    """openai.APITimeoutError is contained as VendorTransportError with timeout signal."""
    import openai

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.chat.completions.create.side_effect = (
        openai.APITimeoutError("request timed out")
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_timeout is True
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
def test_authentication_error_raises_vendor_transport_error() -> None:
    """openai.AuthenticationError maps to auth VendorFailureSignal."""
    import openai

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.chat.completions.create.side_effect = (
        openai.AuthenticationError("invalid key", response=MagicMock(status_code=401), body=None)
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_auth_error is True
def test_connection_error_raises_vendor_transport_error() -> None:
    """openai.APIConnectionError maps to connection VendorFailureSignal."""
    import openai

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.chat.completions.create.side_effect = (
        openai.APIConnectionError(message="connection failed", request=MagicMock())
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_connection_error is True
def test_service_unavailable_503_raises_vendor_transport_error() -> None:
    """HTTP 503 APIStatusError maps to service-unavailable signal."""
    import openai

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.chat.completions.create.side_effect = (
        openai.APIStatusError(
            "service unavailable",
            response=MagicMock(status_code=503),
            body=None,
        )
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_service_unavailable is True
def test_timeout_budget_applied_to_client_options() -> None:
    """TimeoutBudget is forwarded to client.with_options(timeout=...) per §9.3."""
    mock_client = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content="ok"))]
    completion.model = "gpt-4"
    completion.usage = None
    mock_client.with_options.return_value.chat.completions.create.return_value = completion

    transport = _transport_with_client(mock_client)
    transport.complete(_request(), timeout=_budget(read_seconds=12.5))

    mock_client.with_options.assert_called_once()
    _, kwargs = mock_client.with_options.call_args
    assert kwargs.get("timeout") is not None
