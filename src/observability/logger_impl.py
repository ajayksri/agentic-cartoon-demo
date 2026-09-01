"""Logger implementation with structured JSON stdout emission (LLD §6.1, §8.3)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import TextIO

from observability.protocols import CorrelationContext, Tracer
from observability.settings import _ObservabilityConfig
from observability.types import LogEnvelope, LogLevel
from observability.validation import (
    ValidationPipelines,
    _json_default,
    default_validation_pipelines,
    envelope_to_json_dict,
)

_ENVELOPE_FIELD_KEYS = frozenset(
    {
        "workflow_id",
        "task_id",
        "task_attempt",
        "trace_id",
        "span_id",
        "error_class",
        "retryable",
    }
)


class LoggerImpl:
    def __init__(
        self,
        *,
        config: _ObservabilityConfig,
        correlation: CorrelationContext,
        tracer: Tracer,
        pipelines: ValidationPipelines | None = None,
        output: TextIO | None = None,
    ) -> None:
        self._config = config
        self._correlation = correlation
        self._tracer = tracer
        self._pipelines = pipelines or default_validation_pipelines()
        self._output = output if output is not None else sys.stdout

    def emit(self, envelope: LogEnvelope) -> None:
        """Run pipeline §8.3; write one compact JSON line to output."""
        merged = self._pipelines.run_log_validation_pipeline(
            envelope,
            correlation=self._correlation,
            tracer=self._tracer,
            min_level=self._config.log_level,
        )
        if merged is None:
            return

        self._pipelines.validate_bounded_attributes(merged.attributes)
        redacted = self._pipelines.redact_log_envelope(merged)

        payload = json.dumps(
            envelope_to_json_dict(redacted),
            default=_json_default,
            separators=(",", ":"),
        )
        self._output.write(f"{payload}\n")

    def debug(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("DEBUG", event, message, **fields))

    def info(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("INFO", event, message, **fields))

    def warning(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        self.emit(self._build_envelope("WARNING", event, message, **fields))

    def error(
        self,
        event: str,
        message: str,
        *,
        error_class: str,
        retryable: bool,
        **fields: str | int | float | bool,
    ) -> None:
        self.emit(
            self._build_envelope(
                "ERROR",
                event,
                message,
                error_class=error_class,
                retryable=retryable,
                **fields,
            )
        )

    def _build_envelope(
        self,
        level: LogLevel,
        event: str,
        message: str,
        **fields: str | int | float | bool,
    ) -> LogEnvelope:
        """Merge correlation + active trace_id/span_id; set service_name from config."""
        top_level: dict[str, object] = {}
        attributes: dict[str, str | int | float | bool] = {}

        for key, value in fields.items():
            if key in _ENVELOPE_FIELD_KEYS:
                top_level[key] = value
            else:
                attributes[key] = value

        if "workflow_id" not in top_level and self._correlation.workflow_id is not None:
            top_level["workflow_id"] = self._correlation.workflow_id
        if "task_id" not in top_level and self._correlation.task_id is not None:
            top_level["task_id"] = self._correlation.task_id
        if "task_attempt" not in top_level and self._correlation.task_attempt is not None:
            top_level["task_attempt"] = self._correlation.task_attempt

        trace_ctx = self._tracer.current_trace_context()
        if trace_ctx is not None:
            if "trace_id" not in top_level:
                top_level["trace_id"] = trace_ctx.trace_id
            if "span_id" not in top_level:
                top_level["span_id"] = trace_ctx.span_id

        return LogEnvelope(
            event=event,
            level=level,
            timestamp=datetime.now(UTC),
            message=message,
            service_name=self._config.service_name,
            attributes=attributes,
            **top_level,  # type: ignore[arg-type]
        )
