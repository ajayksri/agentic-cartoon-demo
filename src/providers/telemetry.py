"""Provider call telemetry seam."""

from __future__ import annotations

from typing import Literal

from config.types import ProviderId
from observability import get_logger, get_meter, get_tracer
from observability.protocols import Counter, Histogram, Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor

from .constants import (
    LOG_CALL_COMPLETED,
    LOG_CALL_FAILED,
    METRIC_CALL_DURATION_MS,
    METRIC_ERRORS_TOTAL,
    METRIC_TOKENS_TOTAL,
    SPAN_EVENT_COMPLETED,
    SPAN_EVENT_FAILED,
    SPAN_EVENT_STARTED,
    SPAN_GENERATE,
)
from .errors import ProviderError
from .types import TokenUsage


class ProviderTelemetry:
    def __init__(
        self,
        *,
        provider_id: ProviderId,
        logger: Logger | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._logger = logger
        self._tracer = tracer
        self._meter = meter
        self._duration_histogram: Histogram | None = None
        self._input_tokens_counter: Counter | None = None
        self._output_tokens_counter: Counter | None = None
        self._errors_counter: Counter | None = None

    def emit_call_started(self, *, model: str) -> Span:
        self._ensure_instruments()
        tracer = self._tracer or get_tracer()
        span = tracer.start_span(
            SPAN_GENERATE,
            attributes={"provider": self._provider_id.value, "model": model},
        )
        span.__enter__()
        span.add_event(SPAN_EVENT_STARTED)
        return span

    def emit_call_completed(
        self,
        *,
        model: str,
        latency_ms: float,
        token_usage: TokenUsage | None,
        span: Span,
    ) -> None:
        self._finalize_span(span, latency_ms=latency_ms, status="ok")
        logger = self._logger or get_logger()
        fields: dict[str, str | int | float | bool] = {
            "provider": self._provider_id.value,
            "model": model,
            "latency_ms": latency_ms,
        }
        if token_usage is not None:
            if token_usage.input_tokens is not None:
                fields["input_tokens"] = token_usage.input_tokens
            if token_usage.output_tokens is not None:
                fields["output_tokens"] = token_usage.output_tokens
        logger.info(LOG_CALL_COMPLETED, "provider call completed", **fields)

        if self._duration_histogram is not None:
            self._duration_histogram.record(
                latency_ms,
                labels={"provider": self._provider_id.value, "model": model},
            )
        if token_usage is not None:
            if token_usage.input_tokens is not None and self._input_tokens_counter is not None:
                self._input_tokens_counter.add(
                    float(token_usage.input_tokens),
                    labels={"provider": self._provider_id.value, "model": model},
                )
            if token_usage.output_tokens is not None and self._output_tokens_counter is not None:
                self._output_tokens_counter.add(
                    float(token_usage.output_tokens),
                    labels={"provider": self._provider_id.value, "model": model},
                )

    def emit_call_failed(
        self,
        *,
        model: str,
        error: ProviderError,
        latency_ms: float,
        span: Span | None,
    ) -> None:
        logger = self._logger or get_logger()
        self._ensure_instruments()

        if span is not None:
            self._finalize_span(span, latency_ms=latency_ms, status="error")
            span.record_exception(error.__class__.__name__, retryable=error.retryable)

        logger.error(
            LOG_CALL_FAILED,
            "provider call failed",
            error_class=error.error_class.value,
            retryable=error.retryable,
            provider=self._provider_id.value,
            model=model,
            latency_ms=latency_ms,
        )

        if self._errors_counter is not None:
            self._errors_counter.add(
                1.0,
                labels={
                    "provider": self._provider_id.value,
                    "error_class": error.error_class.value,
                    "retryable": str(error.retryable).lower(),
                },
            )

        if span is not None and self._duration_histogram is not None:
            self._duration_histogram.record(
                latency_ms,
                labels={"provider": self._provider_id.value, "model": model},
            )

    def _finalize_span(
        self,
        span: Span,
        *,
        latency_ms: float,
        status: Literal["ok", "error"],
    ) -> None:
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("status", status)
        event = SPAN_EVENT_COMPLETED if status == "ok" else SPAN_EVENT_FAILED
        span.add_event(event)
        span.end(status="OK" if status == "ok" else "ERROR")
        span.__exit__(None, None, None)

    def _ensure_instruments(self) -> None:
        if self._duration_histogram is not None:
            return
        meter = self._meter or get_meter()
        self._duration_histogram = meter.register_histogram(
            MetricDescriptor(
                logical_name=METRIC_CALL_DURATION_MS,
                metric_type="histogram",
                description="Provider vendor-phase call duration",
                allowed_label_keys=frozenset({"provider", "model"}),
                unit="ms",
            )
        )
        self._input_tokens_counter = meter.register_counter(
            MetricDescriptor(
                logical_name=f"{METRIC_TOKENS_TOTAL}_input",
                metric_type="counter",
                description="Provider input token usage",
                allowed_label_keys=frozenset({"provider", "model"}),
            )
        )
        self._output_tokens_counter = meter.register_counter(
            MetricDescriptor(
                logical_name=f"{METRIC_TOKENS_TOTAL}_output",
                metric_type="counter",
                description="Provider output token usage",
                allowed_label_keys=frozenset({"provider", "model"}),
            )
        )
        self._errors_counter = meter.register_counter(
            MetricDescriptor(
                logical_name=METRIC_ERRORS_TOTAL,
                metric_type="counter",
                description="Provider classified errors",
                allowed_label_keys=frozenset({"provider", "error_class", "retryable"}),
            )
        )


class RecordingTelemetry(ProviderTelemetry):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.call_started: list[dict[str, object]] = []
        self.call_completed: list[dict[str, object]] = []
        self.call_failed: list[dict[str, object]] = []
        self.delegated_calls: list[str] = []

    def emit_call_started(self, *, model: str) -> Span:
        span = super().emit_call_started(model=model)
        self.call_started.append({"model": model})
        self.delegated_calls.append("span.start")
        return span

    def emit_call_completed(
        self,
        *,
        model: str,
        latency_ms: float,
        token_usage: TokenUsage | None,
        span: Span,
    ) -> None:
        self.call_completed.append(
            {
                "model": model,
                "latency_ms": latency_ms,
                "token_usage": token_usage,
                "span": span,
            }
        )
        self.delegated_calls.append("log.info")
        super().emit_call_completed(
            model=model,
            latency_ms=latency_ms,
            token_usage=token_usage,
            span=span,
        )

    def emit_call_failed(
        self,
        *,
        model: str,
        error: ProviderError,
        latency_ms: float,
        span: Span | None,
    ) -> None:
        self.call_failed.append(
            {
                "model": model,
                "error": error,
                "latency_ms": latency_ms,
                "span": span,
            }
        )
        self.delegated_calls.append("log.error")
        super().emit_call_failed(
            model=model,
            error=error,
            latency_ms=latency_ms,
            span=span,
        )
