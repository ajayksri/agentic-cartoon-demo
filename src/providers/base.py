"""Shared remote provider orchestration pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from config.types import ProviderConfig, ProviderId, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry

from .cost import CostCalculator
from .error_mapper import VendorErrorMapper
from .errors import ProviderError, ProviderRateLimitError, ProviderTimeoutError
from .injection import InjectionGate
from .rate_limit import ClientRateLimiter
from .response import ResponseAssembler
from .telemetry import ProviderTelemetry
from .timeout import TimeoutContext
from .types import GenerateRequest, GenerateResponse
from .validation import RequestValidator

if TYPE_CHECKING:
    from .vendors._transport import VendorTransport


class _Transport(Protocol):
    def complete(self, request: GenerateRequest, *, timeout: object) -> object:
        ...


@dataclass
class GenerateCallContext:
    request: GenerateRequest
    provider_id: ProviderId
    model: str
    vendor_phase_started_at: float | None = None
    vendor_phase_latency_ms: float | None = None


class BaseRemoteProvider:
    def __init__(
        self,
        *,
        provider_id: ProviderId,
        provider_config: ProviderConfig,
        timeout_config: TimeoutConfig,
        registry: FailureInjectionRegistry | None = None,
        transport: _Transport,
        validator: RequestValidator | None = None,
        injection_gate: InjectionGate | None = None,
        rate_limiter: ClientRateLimiter | None = None,
        timeout_context_factory: Callable[[TimeoutConfig], TimeoutContext] | None = None,
        error_mapper: VendorErrorMapper | None = None,
        cost_calculator: CostCalculator | None = None,
        response_assembler: ResponseAssembler | None = None,
        telemetry: ProviderTelemetry | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._provider_config = provider_config
        self._timeout_config = timeout_config
        self._transport = transport
        self._validator = validator or RequestValidator()
        self._injection_gate = injection_gate or InjectionGate(registry=registry)
        self._rate_limiter = rate_limiter or ClientRateLimiter(
            rate_limit_per_minute=provider_config.rate_limit_per_minute,
            provider_id=provider_id,
        )
        self._error_mapper = error_mapper or VendorErrorMapper(provider_id=provider_id)
        resolved_mapper = self._error_mapper
        self._timeout_context_factory = timeout_context_factory or (
            lambda config: TimeoutContext(
                timeout_config=config,
                provider_id=provider_id,
                error_mapper=resolved_mapper,
            )
        )
        self._cost_calculator = cost_calculator or CostCalculator(
            pricing=provider_config.pricing,
        )
        self._response_assembler = response_assembler or ResponseAssembler()
        self._telemetry = telemetry or ProviderTelemetry(provider_id=provider_id)

    @property
    def provider_id(self) -> ProviderId:
        return self._provider_id

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        from .vendors._transport import VendorTransportError

        self._validator.validate(request)
        model = request.model

        try:
            self._injection_gate.evaluate(request)
        except ProviderError as err:
            self._telemetry.emit_call_failed(
                model=model,
                error=err,
                latency_ms=0.0,
                span=None,
            )
            raise

        try:
            self._rate_limiter.acquire()
        except ProviderRateLimitError as err:
            self._telemetry.emit_call_failed(
                model=model,
                error=err,
                latency_ms=0.0,
                span=None,
            )
            raise

        span = self._telemetry.emit_call_started(model=model)
        ctx = GenerateCallContext(
            request=request,
            provider_id=self._provider_id,
            model=model,
        )
        ctx.vendor_phase_started_at = time.monotonic()

        with self._timeout_context_factory(self._timeout_config) as timeout_ctx:
            try:
                timeout_ctx.check_deadline()
            except ProviderTimeoutError as err:
                ctx.vendor_phase_latency_ms = self._elapsed_ms(ctx)
                self._telemetry.emit_call_failed(
                    model=model,
                    error=err,
                    latency_ms=ctx.vendor_phase_latency_ms,
                    span=span,
                )
                raise

            try:
                vendor_result = self._transport.complete(
                    request,
                    timeout=timeout_ctx.budget,
                )
            except ProviderError as err:
                ctx.vendor_phase_latency_ms = self._elapsed_ms(ctx)
                self._telemetry.emit_call_failed(
                    model=model,
                    error=err,
                    latency_ms=ctx.vendor_phase_latency_ms,
                    span=span,
                )
                raise
            except VendorTransportError as vte:
                error = self._error_mapper.map_vendor_failure(vte.signal)
                ctx.vendor_phase_latency_ms = self._elapsed_ms(ctx)
                self._telemetry.emit_call_failed(
                    model=model,
                    error=error,
                    latency_ms=ctx.vendor_phase_latency_ms,
                    span=span,
                )
                raise error from vte

            try:
                timeout_ctx.check_deadline()
            except ProviderTimeoutError as err:
                ctx.vendor_phase_latency_ms = self._elapsed_ms(ctx)
                self._telemetry.emit_call_failed(
                    model=model,
                    error=err,
                    latency_ms=ctx.vendor_phase_latency_ms,
                    span=span,
                )
                raise

        ctx.vendor_phase_latency_ms = self._elapsed_ms(ctx)
        estimated = self._cost_calculator.estimate(vendor_result.token_usage)  # type: ignore[attr-defined]
        response = self._response_assembler.build_success(
            request=request,
            provider_id=self._provider_id,
            vendor_result=vendor_result,  # type: ignore[arg-type]
            latency_ms=ctx.vendor_phase_latency_ms,
            estimated_cost_usd=estimated,
        )
        self._telemetry.emit_call_completed(
            model=model,
            latency_ms=ctx.vendor_phase_latency_ms,
            token_usage=vendor_result.token_usage,  # type: ignore[attr-defined]
            span=span,
        )
        return response

    @staticmethod
    def _elapsed_ms(ctx: GenerateCallContext) -> float:
        if ctx.vendor_phase_started_at is None:
            return 0.0
        elapsed = max(0.001, (time.monotonic() - ctx.vendor_phase_started_at) * 1000.0)
        return round(elapsed, 3)
