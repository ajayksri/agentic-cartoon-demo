"""Pre-code test mold for PRV-007 — Anthropic VendorErrorMapper (LLD §6.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.types import ProviderId
from providers.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
def test_extract_anthropic_auth_failure_from_fixture() -> None:
    from providers.error_mapper import VendorErrorMapper

    payload = json.loads((_FIXTURES / "anthropic_error_auth.json").read_text(encoding="utf-8"))

    class _AuthError(Exception):
        status_code = 401

        def __str__(self) -> str:
            return payload["error"]["message"]

    signal = VendorErrorMapper.extract_anthropic_failure(_AuthError())
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderAuthenticationError)
    message = str(error)
    assert "invalid x-api-key" not in message
    assert "sk-" not in message
def test_map_anthropic_529_to_provider_response_error() -> None:
    """Anthropic 529 has no OpenAI CG-PRV-003 override."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=529)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderResponseError)
    assert error.retryable is False
def test_map_anthropic_timeout_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(is_timeout=True)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderTimeoutError)
def test_map_anthropic_rate_limit_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=429, is_rate_limit=True)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderRateLimitError)
def test_map_anthropic_schema_validation_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(
        http_status=400,
        vendor_message="output_format json schema mismatch",
        is_schema_validation=True,
    )
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderSchemaValidationError)
def test_map_anthropic_unavailable_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=503, is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
def test_extract_anthropic_connection_error() -> None:
    """LLD §6.2: APIConnectionError → network signal."""
    from providers.error_mapper import VendorErrorMapper

    class _ConnectionError(Exception):
        pass

    signal = VendorErrorMapper.extract_anthropic_failure(_ConnectionError("dns failure"))
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert signal.is_connection_error is True
    from providers.errors import ProviderNetworkError

    assert isinstance(error, ProviderNetworkError)
    assert error.retryable is True
def test_map_anthropic_500_to_provider_response_error() -> None:
    """LLD §6.2: APIStatusError 500 → ProviderResponseError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=500)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderResponseError)
    assert error.retryable is False
def test_map_anthropic_unmapped_to_unknown() -> None:
    """LLD §6.2: unmapped exception → ProviderUnknownError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.errors import ProviderUnknownError
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(exception_type="builtins.RuntimeError")
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnknownError)
    assert error.retryable is False
def test_extract_anthropic_permission_denied_error() -> None:
    """LLD §6.2: PermissionDeniedError → auth signal."""
    from providers.error_mapper import VendorErrorMapper

    class _PermissionDeniedError(Exception):
        status_code = 403

    signal = VendorErrorMapper.extract_anthropic_failure(_PermissionDeniedError("denied"))
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert signal.is_auth_error is True
    assert isinstance(error, ProviderAuthenticationError)
    assert error.retryable is False
def test_map_anthropic_408_to_provider_timeout() -> None:
    """LLD §6.2: APIStatusError 408 → ProviderTimeoutError."""
    from providers.error_mapper import VendorErrorMapper

    class _APIStatusError408(Exception):
        status_code = 408

    signal = VendorErrorMapper.extract_anthropic_failure(_APIStatusError408())
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert signal.is_timeout is True
    assert isinstance(error, ProviderTimeoutError)
    assert error.retryable is True
@pytest.mark.parametrize("http_status", [502, 504])
def test_map_anthropic_unavailable_gateway_errors(http_status: int) -> None:
    """LLD §6.2: APIStatusError 502/504 → ProviderUnavailableError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=http_status, is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
    assert error.retryable is True
def test_extract_anthropic_bad_request_schema_validation() -> None:
    """LLD §6.2: BadRequestError with schema hints → schema validation."""
    from providers.error_mapper import VendorErrorMapper

    class _BadRequestError(Exception):
        status_code = 400

    signal = VendorErrorMapper.extract_anthropic_failure(
        _BadRequestError("output_format json schema mismatch")
    )
    error = VendorErrorMapper(provider_id=ProviderId.ANTHROPIC).map_vendor_failure(signal)

    assert signal.is_schema_validation is True
    assert isinstance(error, ProviderSchemaValidationError)
    assert error.retryable is False
