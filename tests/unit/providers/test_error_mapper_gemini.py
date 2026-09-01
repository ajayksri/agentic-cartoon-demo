"""Pre-code test mold for PRV-007 — Gemini VendorErrorMapper (LLD §6.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.types import ProviderId
from providers.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
def test_map_gemini_resource_exhausted_from_fixture() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    payload = json.loads(
        (_FIXTURES / "gemini_error_resource_exhausted.json").read_text(encoding="utf-8")
    )
    signal = VendorFailureSignal(
        http_status=payload["error"]["code"],
        vendor_message=payload["error"]["message"],
        is_rate_limit=True,
    )
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderRateLimitError)
def test_extract_gemini_deadline_exceeded() -> None:
    from providers.error_mapper import VendorErrorMapper

    class _DeadlineExceeded(Exception):
        pass

    _DeadlineExceeded.__name__ = "DeadlineExceeded"
    signal = VendorErrorMapper.extract_gemini_failure(_DeadlineExceeded())
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderTimeoutError)


def test_extract_gemini_timeout_error() -> None:
    """google.genai httpx timeouts surface as TimeoutError."""
    from providers.error_mapper import VendorErrorMapper

    signal = VendorErrorMapper.extract_gemini_failure(TimeoutError("timed out"))
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert signal.is_timeout is True
    assert isinstance(error, ProviderTimeoutError)


def test_extract_gemini_api_error_rate_limit() -> None:
    """google.genai.errors.ClientError HTTP 429 → rate limit."""
    from providers.error_mapper import VendorErrorMapper

    class ClientError(Exception):
        def __init__(self) -> None:
            super().__init__("quota")
            self.code = 429

    ClientError.__module__ = "google.genai.errors"
    signal = VendorErrorMapper.extract_gemini_failure(ClientError())
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert signal.is_rate_limit is True
    assert isinstance(error, ProviderRateLimitError)
def test_map_gemini_unauthenticated_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(is_auth_error=True)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderAuthenticationError)
def test_map_gemini_service_unavailable_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
def test_map_gemini_schema_validation_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(
        vendor_message="response_schema JSON validation failed",
        is_schema_validation=True,
    )
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderSchemaValidationError)
def test_map_gemini_connection_error_signal() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(is_connection_error=True)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderNetworkError)
def test_map_gemini_unmapped_to_unknown() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(exception_type="builtins.ValueError")
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnknownError)
def test_map_gemini_permission_denied_signal() -> None:
    """LLD §6.3: PermissionDenied → ProviderAuthenticationError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(is_auth_error=True, http_status=403)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderAuthenticationError)
    assert error.retryable is False
def test_extract_gemini_invalid_argument_schema_validation() -> None:
    """LLD §6.3: InvalidArgument with schema hints → schema validation."""
    from providers.error_mapper import VendorErrorMapper

    class _InvalidArgument(Exception):
        pass

    _InvalidArgument.__name__ = "InvalidArgument"
    signal = VendorErrorMapper.extract_gemini_failure(
        _InvalidArgument("response_schema JSON validation failed")
    )
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert signal.is_schema_validation is True
    assert isinstance(error, ProviderSchemaValidationError)
    assert error.retryable is False
@pytest.mark.parametrize("http_status", [401, 403])
def test_map_gemini_google_api_call_error_auth(http_status: int) -> None:
    """LLD §6.3: GoogleAPICallError HTTP 401/403 → ProviderAuthenticationError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=http_status, is_auth_error=True)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderAuthenticationError)
    assert error.retryable is False
def test_map_gemini_google_api_call_error_500() -> None:
    """LLD §6.3: GoogleAPICallError HTTP 500 → ProviderResponseError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.errors import ProviderResponseError
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=500)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderResponseError)
    assert error.retryable is False
def test_map_gemini_google_api_call_error_unlisted_to_unknown() -> None:
    """LLD §6.3 / §14.6: unlisted GoogleAPICallError HTTP → ProviderUnknownError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=520)
    error = VendorErrorMapper(provider_id=ProviderId.GEMINI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnknownError)
    assert error.retryable is False
