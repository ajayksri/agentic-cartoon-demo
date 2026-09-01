"""Pre-code test mold for TQ-004 — MessageSerializer encode/round-trip (LLD §3.2)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config.types import TaskType
from task_queue import (
    TRACE_CARRIER_KEY_TRACEPARENT,
    TRACE_CARRIER_KEY_TRACESTATE,
    TaskMessage,
)


def _valid_message(**overrides: object) -> TaskMessage:
    defaults: dict[str, object] = {
        "task_id": "task-1",
        "workflow_id": "wf-1",
        "task_type": TaskType.COLLECT,
        "attempt": 1,
        "created_at": datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc),
        "payload_reference": "ref://payload/1",
    }
    defaults.update(overrides)
    return TaskMessage(**defaults)  # type: ignore[arg-type]


def test_encode_decode_round_trip() -> None:
    """decode(encode(msg)) equals msg for valid TaskMessage (LLD §3.2)."""
    from task_queue.serializer import MessageSerializer

    message = _valid_message(
        trace_carrier={
            TRACE_CARRIER_KEY_TRACEPARENT: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            TRACE_CARRIER_KEY_TRACESTATE: "vendor=value",
        }
    )
    serializer = MessageSerializer()

    assert serializer.decode(serializer.encode(message)) == message


def test_encode_emits_required_stream_fields() -> None:
    """encode produces all REQUIRED_STREAM_FIELDS keys."""
    from task_queue.serializer import FIELD_ATTEMPT, FIELD_CREATED_AT, MessageSerializer
    from task_queue.serializer import (
        FIELD_PAYLOAD_REFERENCE,
        FIELD_TASK_ID,
        FIELD_TASK_TYPE,
        FIELD_WORKFLOW_ID,
        REQUIRED_STREAM_FIELDS,
    )

    encoded = MessageSerializer().encode(_valid_message())

    assert set(encoded.keys()) >= set(REQUIRED_STREAM_FIELDS)
    assert encoded[FIELD_TASK_ID] == "task-1"
    assert encoded[FIELD_WORKFLOW_ID] == "wf-1"
    assert encoded[FIELD_TASK_TYPE] == TaskType.COLLECT.value
    assert encoded[FIELD_ATTEMPT] == "1"
    assert encoded[FIELD_PAYLOAD_REFERENCE] == "ref://payload/1"
    assert encoded[FIELD_CREATED_AT].endswith("Z")


def test_encode_emits_trace_fields_when_present() -> None:
    """traceparent and tracestate emitted only when present in trace_carrier."""
    from task_queue.serializer import FIELD_TRACEPARENT, FIELD_TRACESTATE, MessageSerializer

    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    encoded = MessageSerializer().encode(
        _valid_message(
            trace_carrier={
                TRACE_CARRIER_KEY_TRACEPARENT: traceparent,
                TRACE_CARRIER_KEY_TRACESTATE: "vendor=value",
                "custom": "ignored",
            }
        )
    )

    assert encoded[FIELD_TRACEPARENT] == traceparent
    assert encoded[FIELD_TRACESTATE] == "vendor=value"
    assert "custom" not in encoded


def test_encode_omits_trace_fields_when_absent() -> None:
    """encode does not emit trace fields when trace_carrier is empty."""
    from task_queue.serializer import FIELD_TRACEPARENT, FIELD_TRACESTATE, MessageSerializer

    encoded = MessageSerializer().encode(_valid_message(trace_carrier={}))

    assert FIELD_TRACEPARENT not in encoded
    assert FIELD_TRACESTATE not in encoded


def test_decode_ignores_unknown_extra_hash_keys() -> None:
    """Unknown extra Redis hash keys are ignored on decode."""
    from task_queue.serializer import MessageSerializer

    serializer = MessageSerializer()
    fields = serializer.encode(_valid_message())
    fields["unexpected_field"] = "ignored"

    decoded = serializer.decode(fields)

    assert decoded == _valid_message()


def test_serializer_accepts_injectable_validator() -> None:
    """MessageSerializer accepts optional injectable MessageValidator."""
    from task_queue.serializer import MessageSerializer
    from task_queue.validation import MessageValidator

    serializer = MessageSerializer(validator=MessageValidator())
    assert serializer.decode(serializer.encode(_valid_message())) == _valid_message()


def test_encode_rejects_invalid_message_before_field_mapping() -> None:
    """encode pre-validates via MessageValidator and rejects attempt=0."""
    from task_queue import InvalidTaskMessageError
    from task_queue.serializer import MessageSerializer

    with pytest.raises(InvalidTaskMessageError):
        MessageSerializer().encode(_valid_message(attempt=0))
