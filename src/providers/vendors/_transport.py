"""Vendor transport types and test doubles."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from config.types import ProviderId

from providers.errors import ProviderError
from providers.internal_types import (
    VendorCallResult,
    VendorFailureSignal,
    VendorTransportError,
)
from providers.types import GenerateRequest

if TYPE_CHECKING:
    from providers.timeout import TimeoutBudget


class VendorTransport(Protocol):
    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: TimeoutBudget,
    ) -> VendorCallResult:
        ...


class StubVendorTransport:
    def __init__(
        self,
        *,
        result: VendorCallResult | Exception | VendorFailureSignal | Callable[
            [GenerateRequest], VendorCallResult | Exception
        ],
        sleep_seconds: float = 0.0,
        provider_id: ProviderId | None = None,
    ) -> None:
        self._result = result
        self._sleep_seconds = sleep_seconds
        self._provider_id = provider_id

    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: TimeoutBudget,
    ) -> VendorCallResult:
        if self._sleep_seconds > 0:
            time.sleep(self._sleep_seconds)

        outcome = self._result(request) if callable(self._result) else self._result

        if isinstance(outcome, VendorCallResult):
            return outcome

        if isinstance(outcome, ProviderError):
            raise outcome

        if isinstance(outcome, VendorFailureSignal):
            raise VendorTransportError(outcome)

        if isinstance(outcome, Exception):
            from providers.error_mapper import VendorErrorMapper

            provider_id = self._provider_id or ProviderId.OPENAI
            if provider_id in (ProviderId.OPENAI, ProviderId.KIMI):
                signal = VendorErrorMapper.extract_openai_failure(outcome)
            elif provider_id is ProviderId.ANTHROPIC:
                signal = VendorErrorMapper.extract_anthropic_failure(outcome)
            elif provider_id is ProviderId.GEMINI:
                signal = VendorErrorMapper.extract_gemini_failure(outcome)
            else:
                signal = VendorFailureSignal(
                    exception_type=f"{type(outcome).__module__}.{type(outcome).__qualname__}",
                )
            raise VendorTransportError(signal)

        raise TypeError(f"unsupported stub transport result: {type(outcome)!r}")


__all__ = [
    "StubVendorTransport",
    "VendorCallResult",
    "VendorFailureSignal",
    "VendorTransport",
    "VendorTransportError",
]
