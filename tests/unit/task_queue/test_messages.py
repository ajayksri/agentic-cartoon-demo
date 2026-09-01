"""Unit tests for TQ-001 — error message templates (LLD §3.8)."""

from __future__ import annotations

import pytest

from task_queue.messages import (
    ack_message,
    connection_message,
    consumer_group_message,
    invalid_message_message,
    stream_not_found_message,
    unavailable_message,
)

_SECRET_PASSWORD = "s3cr3t-p@ssw0rd"
_SECRET_ENV = "REDIS_PASSWORD=leaked"
_PAYLOAD_CONTENTS = "actual-payload-body-should-never-appear"


@pytest.mark.parametrize(
    ("helper", "kwargs", "expected"),
    [
        (
            connection_message,
            {"host": "redis.local", "port": 6379, "reason": "connection refused"},
            "Redis connection failed (redis.local:6379): connection refused",
        ),
        (
            unavailable_message,
            {"operation": "enqueue", "reason": "timeout"},
            "Redis unavailable during enqueue: timeout",
        ),
        (
            invalid_message_message,
            {
                "stream": "cartoon:tasks:collect",
                "delivery_id": "1700000000000-0",
                "missing_fields": ("workflow_id", "attempt"),
            },
            (
                "Invalid task message on stream 'cartoon:tasks:collect', "
                "delivery_id=1700000000000-0: missing or invalid fields: "
                "workflow_id, attempt"
            ),
        ),
        (
            invalid_message_message,
            {
                "stream": "cartoon:tasks:collect",
                "delivery_id": None,
                "missing_fields": ("task_id",),
            },
            (
                "Invalid task message on stream 'cartoon:tasks:collect': "
                "missing or invalid fields: task_id"
            ),
        ),
        (
            consumer_group_message,
            {
                "stream": "cartoon:tasks:collect",
                "group": "cartoon:workers:collect",
                "reason": "NOGROUP",
            },
            (
                "Consumer group error on stream 'cartoon:tasks:collect', "
                "group 'cartoon:workers:collect': NOGROUP"
            ),
        ),
        (
            ack_message,
            {"delivery_id": "1700000000000-0", "reason": "already acknowledged"},
            "ACK failed for delivery_id '1700000000000-0': already acknowledged",
        ),
        (
            stream_not_found_message,
            {"stream": "cartoon:tasks:unknown"},
            "Stream not found: 'cartoon:tasks:unknown'",
        ),
    ],
)
def test_message_template_shape(
    helper: object,
    kwargs: dict[str, object],
    expected: str,
) -> None:
    assert helper(**kwargs) == expected  # type: ignore[operator]


def test_helpers_do_not_embed_password_env_or_payload() -> None:
    """Helpers use only explicit safe parameters; secrets in scope are not leaked."""
    password = _SECRET_PASSWORD
    env_value = _SECRET_ENV
    payload = _PAYLOAD_CONTENTS

    messages = [
        connection_message(host="localhost", port=6379, reason="connection refused"),
        unavailable_message(operation="enqueue", reason="timeout"),
        invalid_message_message(
            stream="cartoon:tasks:collect",
            delivery_id="1-0",
            missing_fields=("payload_reference",),
        ),
        consumer_group_message(
            stream="cartoon:tasks:collect",
            group="cartoon:workers:collect",
            reason="NOGROUP",
        ),
        ack_message(delivery_id="1-0", reason="already acknowledged"),
        stream_not_found_message(stream="cartoon:tasks:unknown"),
    ]

    for message in messages:
        assert password not in message
        assert env_value not in message
        assert payload not in message

    # missing_fields lists field names only, never payload body contents.
    invalid_msg = invalid_message_message(
        stream="cartoon:tasks:collect",
        delivery_id=None,
        missing_fields=("payload_reference",),
    )
    assert "payload_reference" in invalid_msg
    assert payload not in invalid_msg
