"""TaskMessage ↔ Redis stream field map serialization (LLD §3.2)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from .types import (
    TRACE_CARRIER_KEY_TRACEPARENT,
    TRACE_CARRIER_KEY_TRACESTATE,
    TaskMessage,
)
from .validation import MessageValidator

RedisFieldMap = dict[str, str]

FIELD_TASK_ID = "task_id"
FIELD_WORKFLOW_ID = "workflow_id"
FIELD_TASK_TYPE = "task_type"
FIELD_ATTEMPT = "attempt"
FIELD_CREATED_AT = "created_at"
FIELD_PAYLOAD_REFERENCE = "payload_reference"
FIELD_TRACEPARENT = "traceparent"
FIELD_TRACESTATE = "tracestate"

REQUIRED_STREAM_FIELDS: frozenset[str] = frozenset(
    {
        FIELD_TASK_ID,
        FIELD_WORKFLOW_ID,
        FIELD_TASK_TYPE,
        FIELD_ATTEMPT,
        FIELD_CREATED_AT,
        FIELD_PAYLOAD_REFERENCE,
    }
)


class MessageSerializer:
    def __init__(self, validator: MessageValidator | None = None) -> None:
        self._validator = validator or MessageValidator()

    def encode(self, message: TaskMessage) -> RedisFieldMap:
        self._validator.validate(message)

        created_at_utc = message.created_at.astimezone(timezone.utc)
        fields: RedisFieldMap = {
            FIELD_TASK_ID: message.task_id,
            FIELD_WORKFLOW_ID: message.workflow_id,
            FIELD_TASK_TYPE: message.task_type.value,
            FIELD_ATTEMPT: str(message.attempt),
            FIELD_CREATED_AT: created_at_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            FIELD_PAYLOAD_REFERENCE: message.payload_reference,
        }

        traceparent = message.trace_carrier.get(TRACE_CARRIER_KEY_TRACEPARENT)
        if traceparent:
            fields[FIELD_TRACEPARENT] = traceparent

        tracestate = message.trace_carrier.get(TRACE_CARRIER_KEY_TRACESTATE)
        if tracestate:
            fields[FIELD_TRACESTATE] = tracestate

        return fields

    def decode(self, fields: Mapping[str | bytes, str | bytes]) -> TaskMessage:
        normalized = self._normalize_fields(fields)

        message = self._validator.validate_decoded(
            task_id=normalized.get(FIELD_TASK_ID),
            workflow_id=normalized.get(FIELD_WORKFLOW_ID),
            task_type_raw=normalized.get(FIELD_TASK_TYPE),
            attempt_raw=normalized.get(FIELD_ATTEMPT),
            created_at_raw=normalized.get(FIELD_CREATED_AT),
            payload_reference=normalized.get(FIELD_PAYLOAD_REFERENCE),
        )

        trace_carrier: dict[str, str] = {}
        traceparent = normalized.get(FIELD_TRACEPARENT)
        if traceparent:
            trace_carrier[TRACE_CARRIER_KEY_TRACEPARENT] = traceparent

        tracestate = normalized.get(FIELD_TRACESTATE)
        if tracestate:
            trace_carrier[TRACE_CARRIER_KEY_TRACESTATE] = tracestate

        if trace_carrier:
            return TaskMessage(
                task_id=message.task_id,
                workflow_id=message.workflow_id,
                task_type=message.task_type,
                attempt=message.attempt,
                created_at=message.created_at,
                payload_reference=message.payload_reference,
                trace_carrier=trace_carrier,
            )

        return message

    def _normalize_fields(
        self,
        fields: Mapping[str | bytes, str | bytes],
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in fields.items():
            str_key = key.decode() if isinstance(key, bytes) else key
            if isinstance(value, bytes):
                normalized[str_key] = value.decode()
            else:
                normalized[str_key] = value
        return normalized
