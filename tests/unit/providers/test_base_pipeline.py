"""Pre-code test mold for PRV-012 — BaseRemoteProvider pipeline (LLD §12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest

from config.types import ProviderConfig, ProviderId, TimeoutConfig
from providers.errors import ProviderRateLimitError, ProviderTimeoutError
from providers.types import GenerateRequest, ProviderMessage, ProviderMessageRole, TokenUsage

def _request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-4o-mini",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hello"),),
        workflow_id="wf-1",
        task_id="task-1",
    )
def _provider_config() -> ProviderConfig:
    return ProviderConfig(api_key_env="OPENAI_API_KEY", rate_limit_per_minute=None, pricing=None)
def _timeout_config() -> TimeoutConfig:
    return TimeoutConfig(connect_seconds=None, read_seconds=30.0, total_seconds=None)
@dataclass
class _SpyRateLimiter:
    acquire_calls: int = 0

    def acquire(self) -> None:
        self.acquire_calls += 1
@dataclass
class _SpyInjectionGate:
    error: BaseException | None = None

    def evaluate(self, request: GenerateRequest) -> None:
        if self.error is not None:
            raise self.error
@dataclass
class _SpyTelemetry:
    failed: list[dict[str, object]] = field(default_factory=list)
    completed: list[dict[str, object]] = field(default_factory=list)

    def emit_call_started(self, *, model: str) -> object:
        return object()

    def emit_call_completed(
        self,
        *,
        model: str,
        latency_ms: float,
        token_usage: TokenUsage | None,
        span: object,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> None:
        self.completed.append(
            {
                "model": model,
                "latency_ms": latency_ms,
                "token_usage": token_usage,
                "workflow_id": workflow_id,
                "task_id": task_id,
                "task_attempt": task_attempt,
            }
        )

    def emit_call_failed(
        self,
        *,
        model: str,
        error: BaseException,
        latency_ms: float,
        span: object | None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        task_attempt: int | None = None,
    ) -> None:
        self.failed.append(
            {
                "model": model,
                "error": error,
                "latency_ms": latency_ms,
                "span": span,
                "workflow_id": workflow_id,
                "task_id": task_id,
                "task_attempt": task_attempt,
            }
        )
def test_success_path_returns_generate_response() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    transport = StubVendorTransport(
        result=VendorCallResult(content="ok", model="gpt-4o-mini", token_usage=None)
    )
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=transport,
        telemetry=cast(object, _SpyTelemetry()),
    )

    response = provider.generate(_request())

    assert response.content == "ok"
    assert response.provider_id is ProviderId.OPENAI
def test_value_error_from_validator_propagates_without_telemetry() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    telemetry = _SpyTelemetry()
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=StubVendorTransport(
            result=VendorCallResult(content="unused", model="gpt-4o-mini")
        ),
        telemetry=cast(object, telemetry),
    )
    bad_request = GenerateRequest(model="gpt-4o-mini", messages=())

    with pytest.raises(ValueError, match="messages must not be empty"):
        provider.generate(bad_request)

    assert telemetry.failed == []
    assert telemetry.completed == []
def test_injection_failure_does_not_call_rate_limiter() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    rate_limiter = _SpyRateLimiter()
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=StubVendorTransport(
            result=VendorCallResult(content="unused", model="gpt-4o-mini")
        ),
        injection_gate=cast(
            object,
            _SpyInjectionGate(error=ProviderTimeoutError("finj")),
        ),
        rate_limiter=cast(object, rate_limiter),
        telemetry=cast(object, _SpyTelemetry()),
    )

    with pytest.raises(ProviderTimeoutError):
        provider.generate(_request())

    assert rate_limiter.acquire_calls == 0
def test_pre_vendor_failure_emits_telemetry_with_zero_latency() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    telemetry = _SpyTelemetry()
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=StubVendorTransport(
            result=VendorCallResult(content="unused", model="gpt-4o-mini")
        ),
        injection_gate=cast(
            object,
            _SpyInjectionGate(error=ProviderRateLimitError("finj rate")),
        ),
        telemetry=cast(object, telemetry),
    )

    with pytest.raises(ProviderRateLimitError):
        provider.generate(_request())

    assert telemetry.failed[0]["latency_ms"] == 0.0
    assert telemetry.failed[0]["span"] is None
@pytest.mark.prv_tc("040")
def test_success_latency_excludes_injection_and_rate_limit_waiting() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    transport = StubVendorTransport(
        result=VendorCallResult(content="ok", model="gpt-4o-mini"),
        sleep_seconds=0.05,
    )
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=transport,
        telemetry=cast(object, _SpyTelemetry()),
    )

    response = provider.generate(_request())

    assert response.latency_ms >= 1.0
@pytest.mark.prv_tc("020")
def test_deadline_guard_timeout_path_maps_and_emits_failure() -> None:
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorCallResult

    telemetry = _SpyTelemetry()
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=TimeoutConfig(connect_seconds=None, read_seconds=0.01, total_seconds=0.01),
        transport=StubVendorTransport(
            result=VendorCallResult(content="slow", model="gpt-4o-mini"),
            sleep_seconds=0.05,
        ),
        telemetry=cast(object, telemetry),
    )

    with pytest.raises(ProviderTimeoutError):
        provider.generate(_request())

    assert telemetry.failed
    assert telemetry.failed[-1]["latency_ms"] > 0.0
def test_vendor_transport_error_maps_and_emits_failure_telemetry() -> None:
    """LLD §12 path (b): VendorTransportError signal → mapped ProviderError + telemetry."""
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport, VendorFailureSignal

    telemetry = _SpyTelemetry()
    signal = VendorFailureSignal(http_status=429, is_rate_limit=True)
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=StubVendorTransport(result=signal),
        telemetry=cast(object, telemetry),
    )

    with pytest.raises(ProviderRateLimitError):
        provider.generate(_request())

    assert telemetry.failed
    assert isinstance(telemetry.failed[-1]["error"], ProviderRateLimitError)
    assert telemetry.failed[-1]["latency_ms"] > 0.0
def test_programmed_provider_error_from_transport_re_raises_without_wrap() -> None:
    """LLD §12 path (c): programmed ProviderError from transport re-raised unchanged."""
    from providers.base import BaseRemoteProvider
    from providers.vendors._transport import StubVendorTransport

    programmed = ProviderTimeoutError("transport timeout", provider_id=ProviderId.OPENAI)
    telemetry = _SpyTelemetry()
    provider = BaseRemoteProvider(
        provider_id=ProviderId.OPENAI,
        provider_config=_provider_config(),
        timeout_config=_timeout_config(),
        transport=StubVendorTransport(result=programmed),
        telemetry=cast(object, telemetry),
    )

    with pytest.raises(ProviderTimeoutError) as exc_info:
        provider.generate(_request())

    assert exc_info.value is programmed
    assert telemetry.failed
    assert telemetry.failed[-1]["error"] is programmed
