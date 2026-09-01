"""Pre-code test mold for PRV-003 — StubVendorTransport (LLD §4.14)."""

from __future__ import annotations

import time

import pytest

from config.types import ProviderId
from providers.errors import ProviderTimeoutError
from providers.types import GenerateRequest, ProviderMessage, ProviderMessageRole, TokenUsage

def _minimal_request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-4o-mini",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hello"),),
    )
def test_stub_transport_returns_configured_result() -> None:
    """Stub returns programmed VendorCallResult on success path."""
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    expected = VendorCallResult(
        content="stubbed",
        model="gpt-4o-mini",
        token_usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    transport = StubVendorTransport(result=expected)

    result = transport.complete(_minimal_request(), timeout=_timeout_budget())

    assert result.content == "stubbed"
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == 10
def test_stub_transport_sleep_simulates_latency() -> None:
    """Optional sleep_seconds simulates vendor latency (PRV-TC-040 seam)."""
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    transport = StubVendorTransport(
        result=VendorCallResult(content="ok", model="gpt-4o-mini"),
        sleep_seconds=0.05,
    )
    started = time.monotonic()
    transport.complete(_minimal_request(), timeout=_timeout_budget())
    elapsed = time.monotonic() - started

    assert elapsed >= 0.04
def test_stub_transport_re_raises_provider_error_as_is() -> None:
    """Programmed ProviderError subclasses propagate without VendorTransportError wrap."""
    from providers.vendors._transport import StubVendorTransport

    programmed = ProviderTimeoutError("injected timeout", provider_id=ProviderId.OPENAI)
    transport = StubVendorTransport(result=programmed)

    with pytest.raises(ProviderTimeoutError) as exc_info:
        transport.complete(_minimal_request(), timeout=_timeout_budget())

    assert exc_info.value is programmed
def test_stub_transport_maps_generic_exception_to_vendor_transport_error() -> None:
    """Generic exceptions map via injectable extractor to VendorTransportError."""
    from providers.vendors._transport import (
        StubVendorTransport,
        VendorFailureSignal,
        VendorTransportError,
    )

    class _BoomError(RuntimeError):
        pass

    transport = StubVendorTransport(result=_BoomError("boom"))

    with pytest.raises(VendorTransportError) as exc_info:
        transport.complete(_minimal_request(), timeout=_timeout_budget())

    assert isinstance(exc_info.value.signal, VendorFailureSignal)
def _timeout_budget() -> object:
    from providers.timeout import TimeoutBudget

    return TimeoutBudget(
        connect_seconds=5.0,
        read_seconds=30.0,
        total_seconds=None,
        overall_deadline_seconds=30.0,
    )
