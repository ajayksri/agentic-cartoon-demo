"""Log and trace validation pipeline (LLD §8, §10, §15)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Structured observability contracts — every log event
# carries workflow/task correlation and retry metadata required for agent run debugging.
# GUARDRAIL: Audit — enforce required correlation fields on logs for traceable agent decisions.

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import Enum

from observability.errors import InvalidLogEnvelopeError
from observability.protocols import CorrelationContext, Tracer
from observability.redaction import (
    FORBIDDEN_LOG_FIELDS,
    FORBIDDEN_TRACE_ATTRIBUTE_KEYS,
    redact_log_envelope,
)
from observability.types import LogEnvelope, LogLevel

MAX_SCALAR_STRING_LENGTH = 1024

_LOG_LEVEL_ORDER: dict[LogLevel, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}


class EventClass(Enum):
    WORKFLOW = "workflow"
    TASK = "task"
    RETRYABLE_LIFECYCLE = "retryable_lifecycle"
    GENERAL = "general"


WORKFLOW_PREFIXES: tuple[str, ...] = ("workflow_", "state_transition", "human_approval_")
TASK_PREFIXES: tuple[str, ...] = ("task_", "agent_invocation_", "provider_call_")
RETRYABLE_EVENTS: frozenset[str] = frozenset(
    {
        "task_retried",
        "task_redelivered",
    }
)


def classify_event(event: str) -> EventClass:
    if event in RETRYABLE_EVENTS:
        return EventClass.RETRYABLE_LIFECYCLE
    if any(event.startswith(prefix) for prefix in TASK_PREFIXES):
        return EventClass.TASK
    if any(event.startswith(prefix) for prefix in WORKFLOW_PREFIXES):
        return EventClass.WORKFLOW
    return EventClass.GENERAL


def merge_correlation_fields(
    envelope: LogEnvelope,
    correlation: CorrelationContext,
    tracer: Tracer,
) -> LogEnvelope:
    """Non-destructive merge: caller envelope fields win on conflict."""
    updates: dict[str, object] = {}

    if envelope.workflow_id is None and correlation.workflow_id is not None:
        updates["workflow_id"] = correlation.workflow_id
    if envelope.task_id is None and correlation.task_id is not None:
        updates["task_id"] = correlation.task_id
    if envelope.task_attempt is None and correlation.task_attempt is not None:
        updates["task_attempt"] = correlation.task_attempt

    trace_ctx = tracer.current_trace_context()
    if trace_ctx is not None:
        if envelope.trace_id is None:
            updates["trace_id"] = trace_ctx.trace_id
        if envelope.span_id is None:
            updates["span_id"] = trace_ctx.span_id

    if not updates:
        return envelope
    return replace(envelope, **updates)


def check_forbidden_log_fields(envelope: LogEnvelope) -> None:
    """Raise InvalidLogEnvelopeError when forbidden keys appear in attributes."""
    forbidden = envelope.attributes.keys() & FORBIDDEN_LOG_FIELDS
    if forbidden:
        raise InvalidLogEnvelopeError(
            f"Forbidden log attribute keys: {sorted(forbidden)}"
        )


def validate_event_class_requirements(envelope: LogEnvelope) -> None:
    """Raise InvalidLogEnvelopeError when required correlation fields are missing."""
    event_class = classify_event(envelope.event)

    if event_class is EventClass.WORKFLOW:
        if envelope.workflow_id is None:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires workflow_id"
            )
        return

    if event_class is EventClass.TASK:
        if envelope.workflow_id is None:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires workflow_id"
            )
        if envelope.task_id is None:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires task_id"
            )
        return

    if event_class is EventClass.RETRYABLE_LIFECYCLE:
        if envelope.workflow_id is None:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires workflow_id"
            )
        if envelope.task_id is None:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires task_id"
            )
        if envelope.task_attempt is None or envelope.task_attempt < 1:
            raise InvalidLogEnvelopeError(
                f"Event {envelope.event!r} requires task_attempt >= 1"
            )


def validate_error_envelope_fields(envelope: LogEnvelope) -> None:
    """When level is ERROR, require error_class and retryable."""
    if envelope.level != "ERROR":
        return
    if envelope.error_class is None or envelope.retryable is None:
        raise InvalidLogEnvelopeError(
            "ERROR level logs require error_class and retryable"
        )


def passes_log_level_filter(envelope: LogEnvelope, min_level: LogLevel) -> bool:
    """Return False when the envelope is below the configured minimum level."""
    return _LOG_LEVEL_ORDER[envelope.level] >= _LOG_LEVEL_ORDER[min_level]


def validate_bounded_attributes(attributes: Mapping[str, object]) -> None:
    """Reject unbounded strings and non-scalar attribute values."""
    for key, value in attributes.items():
        if not isinstance(value, (str, int, float, bool)):
            raise InvalidLogEnvelopeError(
                f"Attribute {key!r} must be a scalar (str, int, float, bool)"
            )
        if isinstance(value, str) and len(value) > MAX_SCALAR_STRING_LENGTH:
            raise InvalidLogEnvelopeError(
                f"Attribute {key!r} exceeds maximum string length of "
                f"{MAX_SCALAR_STRING_LENGTH}"
            )


def run_log_validation_pipeline(
    envelope: LogEnvelope,
    *,
    correlation: CorrelationContext,
    tracer: Tracer,
    min_level: LogLevel,
) -> LogEnvelope | None:
    """Orchestrate merge and validation steps; return None if below level filter."""
    merged = merge_correlation_fields(envelope, correlation, tracer)
    check_forbidden_log_fields(merged)
    validate_event_class_requirements(merged)
    validate_error_envelope_fields(merged)
    if not passes_log_level_filter(merged, min_level):
        return None
    return merged


def merge_correlation_attributes(
    attributes: Mapping[str, str | int | float | bool],
    correlation: CorrelationContext,
) -> dict[str, str | int | float | bool]:
    """Add correlation fields when bound; caller-supplied keys win."""
    merged = dict(attributes)
    if "workflow_id" not in merged and correlation.workflow_id is not None:
        merged["workflow_id"] = correlation.workflow_id
    if "task_id" not in merged and correlation.task_id is not None:
        merged["task_id"] = correlation.task_id
    if "task_attempt" not in merged and correlation.task_attempt is not None:
        merged["task_attempt"] = correlation.task_attempt
    return merged


def check_forbidden_trace_keys(attributes: Mapping[str, object]) -> None:
    """Raise InvalidLogEnvelopeError when forbidden trace attribute keys are present."""
    forbidden = attributes.keys() & FORBIDDEN_TRACE_ATTRIBUTE_KEYS
    if forbidden:
        raise InvalidLogEnvelopeError(
            f"Forbidden trace attribute keys: {sorted(forbidden)}"
        )


def enforce_bounded_trace_scalar(key: str, value: object) -> str | int | float | bool:
    """Reject unbounded strings and non-scalar trace attribute values."""
    if not isinstance(value, (str, int, float, bool)):
        raise InvalidLogEnvelopeError(
            f"Trace attribute {key!r} must be a scalar (str, int, float, bool)"
        )
    if isinstance(value, str) and len(value) > MAX_SCALAR_STRING_LENGTH:
        raise InvalidLogEnvelopeError(
            f"Trace attribute {key!r} exceeds maximum string length of "
            f"{MAX_SCALAR_STRING_LENGTH}"
        )
    return value


@dataclass(frozen=True, slots=True)
class ValidationPipelines:
    """Frozen references to validation/redaction callables."""

    merge_correlation_fields: Callable[..., LogEnvelope]
    check_forbidden_log_fields: Callable[[LogEnvelope], None]
    validate_event_class_requirements: Callable[[LogEnvelope], None]
    validate_error_envelope_fields: Callable[[LogEnvelope], None]
    validate_bounded_attributes: Callable[[Mapping[str, object]], None]
    passes_log_level_filter: Callable[[LogEnvelope, LogLevel], bool]
    redact_log_envelope: Callable[[LogEnvelope], LogEnvelope]
    run_log_validation_pipeline: Callable[..., LogEnvelope | None]


def default_validation_pipelines() -> ValidationPipelines:
    """Return module-level function references for LoggerImpl and NoOpLogger."""
    return ValidationPipelines(
        merge_correlation_fields=merge_correlation_fields,
        check_forbidden_log_fields=check_forbidden_log_fields,
        validate_event_class_requirements=validate_event_class_requirements,
        validate_error_envelope_fields=validate_error_envelope_fields,
        validate_bounded_attributes=validate_bounded_attributes,
        passes_log_level_filter=passes_log_level_filter,
        redact_log_envelope=redact_log_envelope,
        run_log_validation_pipeline=run_log_validation_pipeline,
    )


def envelope_to_json_dict(envelope: LogEnvelope) -> dict[str, object]:
    """ISO-8601 UTC timestamp; omit None fields; attributes nested."""
    result: dict[str, object] = {}
    for field in fields(envelope):
        value = getattr(envelope, field.name)
        if value is None:
            continue
        if field.name == "timestamp":
            result[field.name] = value.isoformat()
        elif field.name == "attributes":
            if value:
                result[field.name] = dict(value)
        else:
            result[field.name] = value
    return result


def _json_default(obj: object) -> object:
    """datetime → isoformat; fallback str for unsupported types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)
