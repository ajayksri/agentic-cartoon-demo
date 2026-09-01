"""Internal observability facade for API routes."""

from __future__ import annotations

from collections.abc import Mapping

from observability import get_logger, get_meter, get_tracer
from observability.protocols import CorrelationContext, Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor

_HTTP_STATUS_CLASS_LABEL = "http_status_class"
_ROUTE_ID_LABEL = "route_id"

_REQUESTS_COUNTER = MetricDescriptor(
    logical_name="api_requests_total",
    metric_type="counter",
    description="Total API requests by route and status class",
    allowed_label_keys=frozenset({_ROUTE_ID_LABEL, _HTTP_STATUS_CLASS_LABEL}),
)
_DURATION_HISTOGRAM = MetricDescriptor(
    logical_name="api_request_duration_seconds",
    metric_type="histogram",
    description="API request duration by route and status class",
    allowed_label_keys=frozenset({_ROUTE_ID_LABEL, _HTTP_STATUS_CLASS_LABEL}),
    unit="s",
)

_active_recording: RecordingApiTelemetry | None = None


def get_active_tracer() -> Tracer:
    return get_active_telemetry()._tracer


def get_active_correlation_context() -> CorrelationContext:
    if _active_recording is not None and hasattr(_active_recording, "_correlation"):
        return _active_recording._correlation  # type: ignore[attr-defined]
    from observability import get_correlation_context

    return get_correlation_context()


class CapturedLogEvent:
    event: str
    level: str
    fields: dict[str, object]

    def __init__(self, *, event: str, level: str, fields: dict[str, object]) -> None:
        self.event = event
        self.level = level
        self.fields = fields


def get_active_telemetry() -> ApiTelemetry:
    """Return the most recently created recording telemetry for contract tests."""
    if _active_recording is not None:
        return _active_recording
    return ApiTelemetry()


class ApiTelemetry:
    """Structured logging, tracing, and bounded metrics for API routes."""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self._logger = logger or get_logger()
        self._tracer = tracer or get_tracer()
        self._meter = meter or get_meter()
        self._counter = None
        self._histogram = None

    def emit_request_success(
        self, *, route_id: str, http_method: str, status_code: int
    ) -> None:
        del http_method
        self._logger.info(
            "api_request_success",
            "API request completed successfully",
            route_id=route_id,
            status_code=status_code,
        )

    def emit_workflow_initiated(self, *, workflow_id: str) -> None:
        self._logger.info(
            "workflow_initiated",
            "Workflow initiated via API",
            workflow_id=workflow_id,
        )

    def emit_approval_submitted(self, *, workflow_id: str, action: str) -> None:
        self._logger.info(
            "approval_submitted",
            "Approval action submitted via API",
            workflow_id=workflow_id,
            action=action,
        )

    def emit_validation_failed(self, *, route_id: str) -> None:
        self._logger.info(
            "api_validation_failed",
            "API request validation failed",
            route_id=route_id,
            error_class="API_VALIDATION",
        )

    def emit_workflow_error(
        self, *, workflow_id: str | None, error_class: str, route_id: str
    ) -> None:
        self._logger.error(
            "api_workflow_error",
            "Workflow error surfaced via API",
            error_class=error_class,
            retryable=False,
            route_id=route_id,
            workflow_id=workflow_id or "",
        )

    def emit_internal_error(self, *, route_id: str) -> None:
        self._logger.error(
            "api_internal_error",
            "Unexpected internal API error",
            error_class="API_INTERNAL",
            retryable=False,
            route_id=route_id,
        )

    def start_route_span(
        self, name: str, *, attributes: Mapping[str, str | int] = {}
    ) -> Span:
        return self._tracer.start_span(name, attributes=attributes)

    def record_request_metric(
        self, *, route_id: str, status_code: int, duration_seconds: float
    ) -> None:
        labels = {
            _ROUTE_ID_LABEL: route_id,
            _HTTP_STATUS_CLASS_LABEL: _status_class(status_code),
        }
        try:
            if self._counter is None:
                self._counter = self._meter.register_counter(_REQUESTS_COUNTER)
            if self._histogram is None:
                self._histogram = self._meter.register_histogram(_DURATION_HISTOGRAM)
            self._counter.add(1.0, labels=labels)
            self._histogram.record(duration_seconds, labels=labels)
        except ValueError:
            # LLD-API-OBS-001: route_id/http_status_class pending observability co-ownership
            return


class RecordingApiTelemetry(ApiTelemetry):
    """Contract-test seam capturing logs, spans, and metrics."""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        from observability.fakes import CapturingMeter, InMemoryLogger, RecordingTracer
        from observability.settings import _ObservabilityConfig
        from observability.correlation import CorrelationContextImpl
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        config = _ObservabilityConfig(service_name="cartoon-demo-api", log_level="DEBUG")
        correlation = CorrelationContextImpl(propagator=TraceContextTextMapPropagator())
        recording_tracer = RecordingTracer(config=config, correlation=correlation)
        recording_logger = InMemoryLogger(
            config=config,
            correlation=correlation,
            tracer=recording_tracer,
        )
        recording_meter = CapturingMeter(config=config)
        super().__init__(
            logger=logger or recording_logger,
            tracer=tracer or recording_tracer,
            meter=meter or recording_meter,
        )
        self._recording_logger = recording_logger
        self._recording_meter = recording_meter
        self._correlation = correlation
        self.log_events = []
        self.span_names = []
        self.metrics = []
        global _active_recording
        _active_recording = self

    def clear(self) -> None:
        self.log_events.clear()
        self.span_names.clear()
        self.metrics.clear()
        self._recording_logger.records.clear()
        self._recording_meter.emissions.clear()
        if hasattr(self._tracer, "spans"):
            self._tracer.spans.clear()  # type: ignore[attr-defined]

    def emit_request_success(
        self, *, route_id: str, http_method: str, status_code: int
    ) -> None:
        super().emit_request_success(
            route_id=route_id,
            http_method=http_method,
            status_code=status_code,
        )
        self._capture_log("api_request_success", "INFO", route_id=route_id)

    def emit_workflow_initiated(self, *, workflow_id: str) -> None:
        super().emit_workflow_initiated(workflow_id=workflow_id)
        self._capture_log("workflow_initiated", "INFO", workflow_id=workflow_id)

    def emit_approval_submitted(self, *, workflow_id: str, action: str) -> None:
        super().emit_approval_submitted(workflow_id=workflow_id, action=action)
        self._capture_log(
            "approval_submitted",
            "INFO",
            workflow_id=workflow_id,
            action=action,
        )

    def emit_validation_failed(self, *, route_id: str) -> None:
        super().emit_validation_failed(route_id=route_id)
        self._capture_log("api_validation_failed", "INFO", route_id=route_id)

    def emit_workflow_error(
        self, *, workflow_id: str | None, error_class: str, route_id: str
    ) -> None:
        super().emit_workflow_error(
            workflow_id=workflow_id,
            error_class=error_class,
            route_id=route_id,
        )
        self._capture_log(
            "api_workflow_error",
            "ERROR",
            workflow_id=workflow_id,
            error_class=error_class,
            route_id=route_id,
        )

    def emit_internal_error(self, *, route_id: str) -> None:
        super().emit_internal_error(route_id=route_id)
        self._capture_log("api_internal_error", "ERROR", route_id=route_id)

    def start_route_span(
        self, name: str, *, attributes: Mapping[str, str | int] = {}
    ) -> Span:
        self.span_names.append(name)
        return super().start_route_span(name, attributes=attributes)

    def record_request_metric(
        self, *, route_id: str, status_code: int, duration_seconds: float
    ) -> None:
        super().record_request_metric(
            route_id=route_id,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )
        self.metrics.append(
            (
                "api_request",
                {
                    _ROUTE_ID_LABEL: route_id,
                    _HTTP_STATUS_CLASS_LABEL: _status_class(status_code),
                },
                duration_seconds,
            )
        )

    def _capture_log(self, event: str, level: str, **fields: object) -> None:
        self.log_events.append(CapturedLogEvent(event=event, level=level, fields=fields))


def _status_class(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "2xx"
    if 400 <= status_code < 500:
        return "4xx"
    return "5xx"
