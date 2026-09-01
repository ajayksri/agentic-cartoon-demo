"""Vendor failure signal extraction and ProviderError mapping."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Provider error classification — maps vendor failures
# to retryable vs permanent errors so the worker retry policy can decide correctly.
# GUARDRAIL: Execution — classify provider failures so retries are not applied blindly.

from __future__ import annotations

from config.types import ProviderId

from .errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
)
from .messages import client_rate_limit_message, provider_error_message, truncate_vendor_detail
from .types import ProviderErrorClass
from .internal_types import VendorFailureSignal


def _http_status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return int(status)
    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if response_status is not None:
            return int(response_status)
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    return None


def _exception_fqn(exc: BaseException) -> str:
    return f"{type(exc).__module__}.{type(exc).__qualname__}"


def _class_name(exc: BaseException) -> str:
    return type(exc).__name__


def _message(exc: BaseException) -> str:
    return str(exc)


def _openai_schema_signals(exc: BaseException) -> bool:
    message = _message(exc).lower()
    param = getattr(getattr(exc, "param", None), "__str__", lambda: "")()
    if isinstance(getattr(exc, "param", None), str):
        param = exc.param  # type: ignore[attr-defined]
    error_type = getattr(getattr(exc, "type", None), "__str__", lambda: "")()
    if isinstance(getattr(exc, "type", None), str):
        error_type = exc.type  # type: ignore[attr-defined]
    param_str = str(param).lower() if param else ""
    if param_str in {"response_format", "messages"}:
        if "invalid" in str(error_type).lower():
            return True
    if "json_schema" in message or "response_format" in message:
        return True
    return False


def _anthropic_schema_signals(exc: BaseException) -> bool:
    message = _message(exc).lower()
    return "json" in message and ("schema" in message or "output_format" in message)


def _gemini_schema_signals(exc: BaseException) -> bool:
    message = _message(exc).lower()
    return "response_schema" in message or (
        "json" in message and "validation" in message
    )


class VendorErrorMapper:
    def __init__(self, *, provider_id: ProviderId) -> None:
        self._provider_id = provider_id

    def map_vendor_failure(
        self,
        signal: VendorFailureSignal,
        *,
        provider_id: ProviderId | None = None,
    ) -> ProviderError:
        pid = provider_id or signal.provider_id or self._provider_id
        reason = truncate_vendor_detail(signal.vendor_message) or "vendor failure"

        if signal.is_timeout or signal.http_status == 408:
            return self._make(ProviderTimeoutError, pid, reason, signal)

        if signal.is_rate_limit or signal.http_status == 429:
            return self._make(ProviderRateLimitError, pid, reason, signal)

        if signal.is_auth_error or signal.http_status in {401, 403}:
            return self._make(
                ProviderAuthenticationError,
                pid,
                "authentication failed",
                signal,
            )

        if signal.is_service_unavailable or signal.http_status in {502, 503, 504}:
            return self._make(ProviderUnavailableError, pid, reason, signal)

        if signal.is_connection_error:
            return self._make(ProviderNetworkError, pid, reason, signal)

        if signal.is_schema_validation:
            return self._make(ProviderSchemaValidationError, pid, reason, signal)

        if signal.http_status == 529:
            if pid is ProviderId.OPENAI:
                return self._make(ProviderUnavailableError, pid, reason, signal)
            return self._make(ProviderResponseError, pid, reason, signal)

        if signal.http_status == 500:
            return self._make(ProviderResponseError, pid, reason, signal)

        if signal.http_status is not None:
            return self._map_generic_http(pid, signal.http_status, reason, signal)

        if signal.exception_type is not None:
            return self._make(ProviderUnknownError, pid, reason, signal)

        return self._make(ProviderUnknownError, pid, reason, signal)

    def map_timeout(self, *, provider_id: ProviderId) -> ProviderTimeoutError:
        return ProviderTimeoutError(
            provider_error_message(
                code="PRV_TIMEOUT",
                error_class=ProviderErrorClass.TIMEOUT,
                provider_id=provider_id,
                reason="deadline exceeded",
                retryable=True,
            ),
            provider_id=provider_id,
        )

    def map_client_rate_limit(self, *, provider_id: ProviderId) -> ProviderRateLimitError:
        return ProviderRateLimitError(
            client_rate_limit_message(provider_id=provider_id),
            provider_id=provider_id,
        )

    def _make(
        self,
        error_type: type[ProviderError],
        provider_id: ProviderId,
        reason: str,
        signal: VendorFailureSignal,
    ) -> ProviderError:
        error_class = error_type.error_class
        return error_type(
            provider_error_message(
                code=error_type.code,
                error_class=error_class,
                provider_id=provider_id,
                reason=reason,
                retryable=error_type.retryable,
            ),
            provider_id=provider_id,
        )

    def _map_generic_http(
        self,
        provider_id: ProviderId,
        http_status: int,
        reason: str,
        signal: VendorFailureSignal,
    ) -> ProviderError:
        if http_status in {400, 404, 413, 422} or 400 <= http_status < 500:
            return self._make(ProviderResponseError, provider_id, reason, signal)
        if 500 <= http_status < 600:
            return self._make(ProviderUnknownError, provider_id, reason, signal)
        return self._make(ProviderResponseError, provider_id, reason, signal)

    @staticmethod
    def extract_openai_failure(exc: BaseException) -> VendorFailureSignal:
        name = _class_name(exc)
        module = type(exc).__module__
        status = _http_status(exc)
        message = _message(exc)
        is_openai = module == "openai" or module.startswith("openai.")

        if name == "APITimeoutError" or (is_openai and status == 408):
            return VendorFailureSignal(
                http_status=status, is_timeout=True, vendor_message=message
            )
        if name == "APIConnectionError" or name == "_ConnectionError" or (
            is_openai and "Connection" in name
        ):
            return VendorFailureSignal(is_connection_error=True, vendor_message=message)
        if name == "RateLimitError" or status == 429:
            return VendorFailureSignal(
                http_status=429, is_rate_limit=True, vendor_message=message
            )
        if name in {"AuthenticationError", "_AuthError"} or status == 401:
            return VendorFailureSignal(
                http_status=401, is_auth_error=True, vendor_message=message
            )
        if name in {"PermissionDeniedError", "_PermissionDeniedError"} or status == 403:
            return VendorFailureSignal(
                http_status=403, is_auth_error=True, vendor_message=message
            )
        if name in {"BadRequestError", "_BadRequestError"} or status == 400:
            if _openai_schema_signals(exc):
                return VendorFailureSignal(
                    http_status=400,
                    is_schema_validation=True,
                    vendor_message=message,
                )
            return VendorFailureSignal(http_status=400, vendor_message=message)
        if name == "APIStatusError" or (is_openai and status is not None):
            if status in {502, 503, 504}:
                return VendorFailureSignal(
                    http_status=status,
                    is_service_unavailable=True,
                    vendor_message=message,
                )
            if status == 529:
                return VendorFailureSignal(
                    http_status=529,
                    is_service_unavailable=True,
                    vendor_message=message,
                )
            return VendorFailureSignal(http_status=status, vendor_message=message)

        if status == 408:
            return VendorFailureSignal(http_status=408, is_timeout=True, vendor_message=message)

        return VendorFailureSignal(exception_type=_exception_fqn(exc), vendor_message=message)

    @staticmethod
    def extract_anthropic_failure(exc: BaseException) -> VendorFailureSignal:
        name = _class_name(exc)
        module = type(exc).__module__
        status = _http_status(exc)
        message = _message(exc)
        is_anthropic = module == "anthropic" or module.startswith("anthropic.")

        if name == "APITimeoutError" or (is_anthropic and status == 408):
            return VendorFailureSignal(
                http_status=status, is_timeout=True, vendor_message=message
            )
        if name == "APIConnectionError" or name == "_ConnectionError" or (
            is_anthropic and "Connection" in name
        ):
            return VendorFailureSignal(is_connection_error=True, vendor_message=message)
        if name == "RateLimitError" or status == 429:
            return VendorFailureSignal(
                http_status=429, is_rate_limit=True, vendor_message=message
            )
        if name in {"AuthenticationError", "_AuthError"} or status == 401:
            return VendorFailureSignal(
                http_status=401, is_auth_error=True, vendor_message=message
            )
        if name in {"PermissionDeniedError", "_PermissionDeniedError"} or status == 403:
            return VendorFailureSignal(
                http_status=403, is_auth_error=True, vendor_message=message
            )
        if name in {"BadRequestError", "_BadRequestError"} or status == 400:
            if _anthropic_schema_signals(exc):
                return VendorFailureSignal(
                    http_status=400,
                    is_schema_validation=True,
                    vendor_message=message,
                )
            return VendorFailureSignal(http_status=400, vendor_message=message)
        if name == "APIStatusError" or (is_anthropic and status is not None):
            if status in {502, 503, 504}:
                return VendorFailureSignal(
                    http_status=status,
                    is_service_unavailable=True,
                    vendor_message=message,
                )
            return VendorFailureSignal(http_status=status, vendor_message=message)

        if status == 408:
            return VendorFailureSignal(http_status=408, is_timeout=True, vendor_message=message)

        return VendorFailureSignal(exception_type=_exception_fqn(exc), vendor_message=message)

    @staticmethod
    def extract_gemini_failure(exc: BaseException) -> VendorFailureSignal:
        name = _class_name(exc)
        module = type(exc).__module__
        status = _http_status(exc)
        message = _message(exc)
        is_google = module.startswith("google.")

        if name == "DeadlineExceeded" or isinstance(exc, TimeoutError) or name in {
            "TimeoutException",
            "ReadTimeout",
        }:
            return VendorFailureSignal(is_timeout=True, vendor_message=message)
        if name in {"ServiceUnavailable", "Unavailable"}:
            return VendorFailureSignal(is_service_unavailable=True, vendor_message=message)
        if name == "ResourceExhausted":
            return VendorFailureSignal(is_rate_limit=True, vendor_message=message)
        if name == "Unauthenticated":
            return VendorFailureSignal(is_auth_error=True, vendor_message=message)
        if name == "PermissionDenied":
            return VendorFailureSignal(is_auth_error=True, vendor_message=message)
        if name == "InvalidArgument":
            if _gemini_schema_signals(exc):
                return VendorFailureSignal(is_schema_validation=True, vendor_message=message)
            return VendorFailureSignal(vendor_message=message)
        if name in {"TransportError", "ConnectError"} or isinstance(exc, ConnectionError):
            return VendorFailureSignal(is_connection_error=True, vendor_message=message)
        if name in {"GoogleAPICallError", "APIError", "ClientError", "ServerError"} or (
            is_google and status is not None
        ):
            if status == 408:
                return VendorFailureSignal(http_status=408, is_timeout=True, vendor_message=message)
            if status == 429:
                return VendorFailureSignal(
                    http_status=429, is_rate_limit=True, vendor_message=message
                )
            if status in {401, 403}:
                return VendorFailureSignal(
                    http_status=status, is_auth_error=True, vendor_message=message
                )
            if status in {502, 503, 504}:
                return VendorFailureSignal(
                    http_status=status,
                    is_service_unavailable=True,
                    vendor_message=message,
                )
            if status == 500:
                return VendorFailureSignal(http_status=500, vendor_message=message)
            return VendorFailureSignal(http_status=status, vendor_message=message)

        return VendorFailureSignal(exception_type=_exception_fqn(exc), vendor_message=message)
