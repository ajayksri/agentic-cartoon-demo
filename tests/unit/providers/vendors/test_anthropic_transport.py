"""Pre-code test mold for PRV-016 — AnthropicTransport (LLD §4.13, §6.2, §9.3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from providers import GenerateRequest, ProviderMessage, ProviderMessageRole, TokenUsage

def _request() -> GenerateRequest:
    return GenerateRequest(
        model="claude-3",
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
    from providers.vendors.anthropic import AnthropicTransport

    return AnthropicTransport(api_key="test-key", client=mock_client)
def test_complete_success_maps_vendor_call_result() -> None:
    """Successful Messages API response maps to VendorCallResult."""
    from providers.vendors._transport import VendorCallResult

    mock_client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text="anthropic reply")]
    message.usage = MagicMock(input_tokens=20, output_tokens=8)
    mock_client.with_options.return_value.messages.create.return_value = message
    mock_client.with_options.return_value.messages.create.return_value.model = "claude-3"

    transport = _transport_with_client(mock_client)
    result = transport.complete(_request(), timeout=_budget())

    assert isinstance(result, VendorCallResult)
    assert result.content == "anthropic reply"
    assert result.token_usage == TokenUsage(input_tokens=20, output_tokens=8)
def test_api_timeout_error_raises_vendor_transport_error() -> None:
    """anthropic.APITimeoutError is contained as VendorTransportError."""
    import anthropic

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = anthropic.APITimeoutError(
        "request timed out"
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_timeout is True
def test_rate_limit_error_raises_vendor_transport_error() -> None:
    """anthropic.RateLimitError maps to rate-limit VendorFailureSignal."""
    import anthropic

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = anthropic.RateLimitError(
        "rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_rate_limit is True
def test_authentication_error_raises_vendor_transport_error() -> None:
    """anthropic.AuthenticationError maps to auth VendorFailureSignal."""
    import anthropic

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = (
        anthropic.AuthenticationError(
            "invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_auth_error is True
def test_connection_error_raises_vendor_transport_error() -> None:
    """anthropic.APIConnectionError maps to connection VendorFailureSignal."""
    import anthropic

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = (
        anthropic.APIConnectionError(message="connection failed", request=MagicMock())
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_connection_error is True
def test_service_unavailable_503_raises_vendor_transport_error() -> None:
    """HTTP 503 APIStatusError maps to service-unavailable signal."""
    import anthropic

    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = anthropic.APIStatusError(
        "service unavailable",
        response=MagicMock(status_code=503),
        body=None,
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_service_unavailable is True
def test_status_529_maps_to_provider_response_not_unavailable() -> None:
    """Anthropic HTTP 529 maps to ProviderResponseError via mapper (no OpenAI override)."""
    import anthropic

    from config.types import ProviderId
    from providers import ProviderResponseError
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.with_options.return_value.messages.create.side_effect = anthropic.APIStatusError(
        "overloaded",
        response=MagicMock(status_code=529),
        body=None,
    )

    transport = _transport_with_client(mock_client)

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    mapper = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC)
    mapped = mapper.map_vendor_failure(exc_info.value.signal)

    assert isinstance(mapped, ProviderResponseError)
    assert mapped.retryable is False
