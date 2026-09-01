"""Pre-code test mold for TQ-003 — MessageValidator (LLD §3.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config.types import TaskType
from task_queue import InvalidTaskMessageError, TaskMessage


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


def test_valid_message_passes_validation() -> None:
    """Valid TaskMessage passes validate without raising."""
    from task_queue.validation import MessageValidator

    MessageValidator().validate(_valid_message())


def test_required_fields_tuple_matches_lld() -> None:
    """REQUIRED_FIELDS matches LLD §3.1 tuple."""
    from task_queue.validation import MessageValidator

    assert MessageValidator.REQUIRED_FIELDS == (
        "task_id",
        "workflow_id",
        "task_type",
        "attempt",
        "created_at",
        "payload_reference",
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("task_id", ""),
        ("task_id", "   "),
        ("workflow_id", ""),
        ("workflow_id", "\t"),
        ("payload_reference", ""),
        ("payload_reference", "  "),
    ],
)
def test_empty_or_whitespace_string_fields_rejected(
    field_name: str,
    value: str,
) -> None:
    """Empty/whitespace task_id, workflow_id, payload_reference → missing_fields."""
    from task_queue.validation import MessageValidator

    message = _valid_message(**{field_name: value})

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageValidator().validate(message)

    assert field_name in exc_info.value.missing_fields


@pytest.mark.parametrize("attempt", [0, -1])
def test_invalid_attempt_rejected(attempt: int) -> None:
    """attempt < 1 raises InvalidTaskMessageError with attempt in missing_fields."""
    from task_queue.validation import MessageValidator

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageValidator().validate(_valid_message(attempt=attempt))

    assert "attempt" in exc_info.value.missing_fields


def test_validate_does_not_inspect_trace_carrier() -> None:
    """trace_carrier keys are not validated on validate()."""
    from task_queue.validation import MessageValidator

    MessageValidator().validate(
        _valid_message(trace_carrier={"bogus": "value"})
    )


def test_validate_decoded_round_trips_valid_strings() -> None:
    """validate_decoded parses valid raw strings into equivalent TaskMessage."""
    from task_queue.validation import MessageValidator

    created = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    message = MessageValidator().validate_decoded(
        task_id="task-1",
        workflow_id="wf-1",
        task_type_raw=TaskType.COLLECT.value,
        attempt_raw="1",
        created_at_raw="2026-08-31T12:00:00.000000Z",
        payload_reference="ref://payload/1",
    )

    assert message.task_id == "task-1"
    assert message.workflow_id == "wf-1"
    assert message.task_type == TaskType.COLLECT
    assert message.attempt == 1
    assert message.created_at == created
    assert message.payload_reference == "ref://payload/1"


def test_validate_decoded_invalid_task_type() -> None:
    """Invalid task_type string raises InvalidTaskMessageError."""
    from task_queue.validation import MessageValidator

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageValidator().validate_decoded(
            task_id="task-1",
            workflow_id="wf-1",
            task_type_raw="NOT_A_TASK",
            attempt_raw="1",
            created_at_raw="2026-08-31T12:00:00.000000Z",
            payload_reference="ref://payload/1",
        )

    assert "task_type" in exc_info.value.missing_fields


def test_validate_decoded_malformed_created_at() -> None:
    """Malformed created_at raises InvalidTaskMessageError."""
    from task_queue.validation import MessageValidator

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageValidator().validate_decoded(
            task_id="task-1",
            workflow_id="wf-1",
            task_type_raw=TaskType.COLLECT.value,
            attempt_raw="1",
            created_at_raw="not-a-timestamp",
            payload_reference="ref://payload/1",
        )

    assert "created_at" in exc_info.value.missing_fields


def test_validate_decoded_missing_workflow_id() -> None:
    """Missing workflow_id in decoded fields lists workflow_id in missing_fields."""
    from task_queue.validation import MessageValidator

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        MessageValidator().validate_decoded(
            task_id="task-1",
            workflow_id=None,
            task_type_raw=TaskType.COLLECT.value,
            attempt_raw="1",
            created_at_raw="2026-08-31T12:00:00.000000Z",
            payload_reference="ref://payload/1",
        )

    assert "workflow_id" in exc_info.value.missing_fields


def test_validate_decoded_never_returns_partial_message() -> None:
    """validate_decoded raises instead of returning a partial TaskMessage."""
    from task_queue.validation import MessageValidator

    with pytest.raises(InvalidTaskMessageError):
        MessageValidator().validate_decoded(
            task_id=None,
            workflow_id=None,
            task_type_raw=None,
            attempt_raw=None,
            created_at_raw=None,
            payload_reference=None,
        )
