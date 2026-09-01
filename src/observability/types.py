"""Public type definitions for the observability module contract boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
MetricType = Literal["counter", "histogram", "gauge"]
SpanStatus = Literal["OK", "ERROR", "UNSET"]

# Bounded label keys permitted by ACD-NFR-005 (illustrative allow-list).
BOUNDED_METRIC_LABEL_KEYS: frozenset[str] = frozenset(
    {
        "agent",
        "provider",
        "model",
        "task_type",
        "workflow_stage",
        "status",
        "result",
        "outcome",
        "error_class",
        "retryable",
        "resolution",
        "kind",
        "subcommand_id",
        "exit_code_class",
        "signal",
        "repair_action",
        "process_kind",
        "route_id",
        "http_status_class",
    }
)

# Label keys that MUST NOT appear on metrics (ACD-NFR-005).
FORBIDDEN_METRIC_LABEL_KEYS: frozenset[str] = frozenset(
    {
        "workflow_id",
        "task_id",
        "prompt",
        "response",
        "url",
        "error_message",
    }
)


@dataclass(frozen=True, slots=True)
class LogEnvelope:
    """Structured log record emitted by Logger."""

    event: str
    level: LogLevel
    timestamp: datetime
    message: str
    service_name: str
    workflow_id: str | None = None
    task_id: str | None = None
    task_attempt: int | None = None
    trace_id: str | None = None
    span_id: str | None = None
    error_class: str | None = None
    retryable: bool | None = None
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricDescriptor:
    """Registration metadata for a metric instrument."""

    logical_name: str
    metric_type: MetricType
    description: str
    allowed_label_keys: frozenset[str]
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Serializable distributed trace identity (OTel-compatible)."""

    trace_id: str
    span_id: str
    trace_flags: int = 1
    is_remote: bool = False
