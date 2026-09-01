"""Pre-code test mold for PRV-017 — GeminiTransport (LLD §4.13, §6.3, §9.3)."""

from __future__ import annotations

import importlib
import warnings
from unittest.mock import MagicMock

import pytest

from providers import GenerateRequest, ProviderMessage, ProviderMessageRole


def _request() -> GenerateRequest:
    return GenerateRequest(
        model="gemini-pro",
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
    from providers.vendors.gemini import GeminiTransport

    return GeminiTransport(api_key="test-key", client=mock_client)


def test_gemini_module_import_emits_no_deprecation_warning() -> None:
    """google.generativeai is retired; importing the adapter must not emit FutureWarning."""
    import providers.vendors.gemini as gemini_mod

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(gemini_mod)

    deprecations = [
        w
        for w in caught
        if issubclass(w.category, (DeprecationWarning, FutureWarning))
        and "google.generativeai" in str(w.message)
    ]
    assert deprecations == []


def test_complete_success_maps_vendor_call_result() -> None:
    """Successful generate_content maps to VendorCallResult."""
    from providers.vendors._transport import VendorCallResult
    from providers.vendors.gemini import GeminiTransport

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "gemini reply"
    mock_response.usage_metadata = MagicMock(prompt_token_count=15, candidates_token_count=6)
    mock_client.models.generate_content.return_value = mock_response

    transport = _transport_with_client(mock_client)
    result = transport.complete(_request(), timeout=_budget())

    assert isinstance(result, VendorCallResult)
    assert isinstance(transport, GeminiTransport)
    assert result.content == "gemini reply"
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == 15
    assert result.token_usage.output_tokens == 6


def test_deadline_exceeded_raises_vendor_transport_error() -> None:
    """TimeoutError from the GenAI SDK maps to timeout signal."""
    from providers.vendors._transport import VendorTransportError

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("deadline")

    transport = _transport_with_client(mock_client)
    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_timeout is True


def test_resource_exhausted_raises_vendor_transport_error() -> None:
    """HTTP 429 from google.genai.errors maps to rate-limit VendorFailureSignal."""
    from providers.vendors._transport import VendorTransportError

    class ClientError(Exception):
        def __init__(self) -> None:
            super().__init__("quota")
            self.code = 429

    ClientError.__module__ = "google.genai.errors"
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ClientError()

    transport = _transport_with_client(mock_client)
    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_rate_limit is True


def test_unauthenticated_raises_vendor_transport_error() -> None:
    """HTTP 401 from google.genai.errors maps to auth VendorFailureSignal."""
    from providers.vendors._transport import VendorTransportError

    class ClientError(Exception):
        def __init__(self) -> None:
            super().__init__("bad key")
            self.code = 401

    ClientError.__module__ = "google.genai.errors"
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ClientError()

    transport = _transport_with_client(mock_client)
    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_auth_error is True


def test_service_unavailable_raises_vendor_transport_error() -> None:
    """HTTP 503 from google.genai.errors maps to service-unavailable VendorFailureSignal."""
    from providers.vendors._transport import VendorTransportError

    class ServerError(Exception):
        def __init__(self) -> None:
            super().__init__("down")
            self.code = 503

    ServerError.__module__ = "google.genai.errors"
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ServerError()

    transport = _transport_with_client(mock_client)
    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_service_unavailable is True


def test_connection_error_raises_vendor_transport_error() -> None:
    """TransportError / connection failures map to network signal."""
    from providers.vendors._transport import VendorTransportError

    class _TransportError(Exception):
        pass

    _TransportError.__name__ = "TransportError"
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _TransportError("ssl error")

    transport = _transport_with_client(mock_client)
    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_request(), timeout=_budget())

    assert exc_info.value.signal.is_connection_error is True


def test_timeout_budget_passed_in_http_options() -> None:
    """TimeoutBudget.overall_deadline_seconds forwarded as HttpOptions timeout in ms per §9.3."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "ok"
    mock_response.usage_metadata = None
    mock_client.models.generate_content.return_value = mock_response

    transport = _transport_with_client(mock_client)
    transport.complete(_request(), timeout=_budget(read_seconds=8.0))

    config = mock_client.models.generate_content.call_args.kwargs.get("config")
    assert config is not None
    assert config["http_options"]["timeout"] == 8000
    assert config["system_instruction"] == "system"
