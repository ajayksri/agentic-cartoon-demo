"""Pre-code test mold for TQ-004 — MessageSerializer decode errors (LLD §3.2)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from task_queue import InvalidTaskMessageError


def test_decode_missing_workflow_id_lists_missing_fields() -> None:
    """Corrupt field map missing workflow_id → InvalidTaskMessageError (TQ-TC-010 seam)."""
    from task_queue.serializer import MessageSerializer

    fields = {
        "task_id": "task-1",
        "task_type": TaskType.COLLECT.value,
        "attempt": "1",
        "created_at": "2026-08-31T12:00:00.000000Z",
        "payload_reference": "ref://payload/1",
    }

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageSerializer().decode(fields)

    assert "workflow_id" in exc_info.value.missing_fields


def test_decode_missing_task_id() -> None:
    """Missing task_id in field map lists task_id in missing_fields."""
    from task_queue.serializer import MessageSerializer

    fields = {
        "workflow_id": "wf-1",
        "task_type": TaskType.COLLECT.value,
        "attempt": "1",
        "created_at": "2026-08-31T12:00:00.000000Z",
        "payload_reference": "ref://payload/1",
    }

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageSerializer().decode(fields)

    assert "task_id" in exc_info.value.missing_fields


def test_decode_invalid_attempt_string() -> None:
    """Non-numeric attempt string lists attempt in missing_fields."""
    from task_queue.serializer import MessageSerializer

    fields = {
        "task_id": "task-1",
        "workflow_id": "wf-1",
        "task_type": TaskType.COLLECT.value,
        "attempt": "zero",
        "created_at": "2026-08-31T12:00:00.000000Z",
        "payload_reference": "ref://payload/1",
    }

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageSerializer().decode(fields)

    assert "attempt" in exc_info.value.missing_fields


def test_decode_attempt_zero_rejected() -> None:
    """attempt=0 in field map lists attempt in missing_fields."""
    from task_queue.serializer import MessageSerializer

    fields = {
        "task_id": "task-1",
        "workflow_id": "wf-1",
        "task_type": TaskType.COLLECT.value,
        "attempt": "0",
        "created_at": "2026-08-31T12:00:00.000000Z",
        "payload_reference": "ref://payload/1",
    }

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageSerializer().decode(fields)

    assert "attempt" in exc_info.value.missing_fields


def test_decode_normalizes_bytes_keys_and_values() -> None:
    """decode normalizes redis-py bytes responses to str before validation."""
    from datetime import datetime, timezone

    from config.types import TaskType
    from task_queue import TaskMessage
    from task_queue.serializer import MessageSerializer

    fields = {
        b"task_id": b"task-1",
        b"workflow_id": b"wf-1",
        b"task_type": TaskType.COLLECT.value.encode(),
        b"attempt": b"1",
        b"created_at": b"2026-08-31T12:00:00.000000Z",
        b"payload_reference": b"ref://payload/1",
    }

    decoded = MessageSerializer().decode(fields)

    assert decoded == TaskMessage(
        task_id="task-1",
        workflow_id="wf-1",
        task_type=TaskType.COLLECT,
        attempt=1,
        created_at=datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc),
        payload_reference="ref://payload/1",
    )
