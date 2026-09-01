"""Pre-code test mold for PRV-007 — OpenAI VendorErrorMapper (LLD §6.1, §14)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.types import ProviderId
from providers.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)
from providers.types import ProviderErrorClass
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "providers"
@pytest.mark.prv_tc("010")
def test_map_timeout_returns_provider_timeout_error() -> None:
    from providers.error_mapper import VendorErrorMapper

    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_timeout(
        provider_id=ProviderId.OPENAI
    )

    assert isinstance(error, ProviderTimeoutError)
    assert error.code == "PRV_TIMEOUT"
    assert error.retryable is True
def test_map_client_rate_limit_returns_provider_rate_limit_error() -> None:
    """Client-side token bucket exhaustion — distinct from vendor HTTP 429 (LLD §4.7, §14.2)."""
    from providers.error_mapper import VendorErrorMapper

    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_client_rate_limit(
        provider_id=ProviderId.OPENAI
    )

    assert isinstance(error, ProviderRateLimitError)
    assert error.code == "PRV_RATE"
    assert error.retryable is True
    message = str(error).lower()
    assert "client rate limit exceeded" in message
    assert "429" not in message
@pytest.mark.prv_tc("011")
def test_map_vendor_failure_rate_limit_from_fixture() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    payload = json.loads((_FIXTURES / "openai_error_429.json").read_text(encoding="utf-8"))
    signal = VendorFailureSignal(
        http_status=429,
        vendor_message=payload["error"]["message"],
        is_rate_limit=True,
        provider_id=ProviderId.OPENAI,
    )

    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderRateLimitError)
    assert error.error_class is ProviderErrorClass.RATE_LIMIT
    assert error.retryable is True
@pytest.mark.prv_tc("012")
def test_extract_openai_authentication_error() -> None:
    from providers.error_mapper import VendorErrorMapper

    class _AuthError(Exception):
        status_code = 401

    signal = VendorErrorMapper.extract_openai_failure(_AuthError("invalid key"))

    assert signal.is_auth_error is True
    mapped = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)
    assert isinstance(mapped, ProviderAuthenticationError)
    assert mapped.retryable is False
@pytest.mark.prv_tc("013")
def test_map_openai_503_to_provider_unavailable() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=503, is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
    assert error.retryable is True
@pytest.mark.prv_tc("014")
def test_map_openai_connection_error_to_network_error() -> None:
    from providers.error_mapper import VendorErrorMapper

    class _ConnectionError(Exception):
        pass

    signal = VendorErrorMapper.extract_openai_failure(_ConnectionError("dns"))
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderNetworkError)
@pytest.mark.prv_tc("015")
def test_map_openai_schema_validation_error() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(
        http_status=400,
        vendor_message="Invalid response_format json_schema",
        is_schema_validation=True,
    )
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderSchemaValidationError)
    assert error.retryable is False
@pytest.mark.prv_tc("016")
def test_map_unmapped_openai_failure_to_unknown() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(exception_type="builtins.RuntimeError")
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnknownError)
    assert error.retryable is False
def test_openai_529_override_maps_to_provider_unavailable() -> None:
    """CG-PRV-003: OpenAI HTTP 529 → ProviderUnavailableError (retryable)."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=529, is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
    assert error.retryable is True
def test_map_openai_500_to_provider_response_error() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=500)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderResponseError)
    assert error.retryable is False
@pytest.mark.prv_tc("018")
def test_auth_error_message_omits_secret_values() -> None:
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    secret = "sk-live-supersecretvalue1234567890"
    signal = VendorFailureSignal(
        http_status=401,
        vendor_message="invalid key",
        is_auth_error=True,
    )
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert secret not in str(error)
def test_extract_openai_permission_denied_error() -> None:
    """LLD §6.1: PermissionDeniedError → auth signal."""
    from providers.error_mapper import VendorErrorMapper

    class _PermissionDeniedError(Exception):
        status_code = 403

    signal = VendorErrorMapper.extract_openai_failure(_PermissionDeniedError("forbidden"))
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert signal.is_auth_error is True
    assert isinstance(error, ProviderAuthenticationError)
    assert error.retryable is False
def test_map_openai_408_to_provider_timeout() -> None:
    """LLD §6.1: APIStatusError 408 → ProviderTimeoutError."""
    from providers.error_mapper import VendorErrorMapper

    class _APIStatusError408(Exception):
        status_code = 408

    signal = VendorErrorMapper.extract_openai_failure(_APIStatusError408())
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert signal.is_timeout is True
    assert isinstance(error, ProviderTimeoutError)
    assert error.retryable is True
@pytest.mark.parametrize("http_status", [502, 504])
def test_map_openai_unavailable_gateway_errors(http_status: int) -> None:
    """LLD §6.1: APIStatusError 502/504 → ProviderUnavailableError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=http_status, is_service_unavailable=True)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnavailableError)
    assert error.retryable is True
def test_extract_openai_bad_request_schema_validation() -> None:
    """LLD §6.1: BadRequestError with schema signals → schema validation."""
    from providers.error_mapper import VendorErrorMapper

    class _BadRequestError(Exception):
        status_code = 400

    signal = VendorErrorMapper.extract_openai_failure(
        _BadRequestError("Invalid json_schema in response_format")
    )
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert signal.is_schema_validation is True
    assert isinstance(error, ProviderSchemaValidationError)
    assert error.retryable is False
def test_map_openai_generic_api_status_404_to_response_error() -> None:
    """LLD §14.6: residual APIStatusError 404 → ProviderResponseError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=404)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderResponseError)
    assert error.retryable is False
def test_map_openai_generic_api_status_unlisted_5xx_to_unknown() -> None:
    """LLD §14.6: unlisted 5xx → ProviderUnknownError."""
    from providers.error_mapper import VendorErrorMapper
    from providers.vendors._transport import VendorFailureSignal

    signal = VendorFailureSignal(http_status=520)
    error = VendorErrorMapper(provider_id=ProviderId.OPENAI).map_vendor_failure(signal)

    assert isinstance(error, ProviderUnknownError)
    assert error.retryable is False
