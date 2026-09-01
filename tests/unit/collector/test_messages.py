"""Unit tests for COL-002 — error and rejection message helpers (LLD §4.5)."""

from __future__ import annotations

import pytest

from collector.constants import ERROR_DETAIL_MAX_LENGTH
from collector.messages import collector_error_message, rejection_detail
from collector.types import RejectionReason

_FAKE_RAW_BODY = b'{"id": 1, "title": "secret story", "by": "hn-user"}'


@pytest.mark.parametrize(
    ("code", "reason", "retryable", "expected"),
    [
        ("COL_FETCH", "connection refused", True, "COL_FETCH: connection refused (retryable=True)"),
        (
            "COL_RESPONSE",
            "feed not valid JSON array",
            False,
            "COL_RESPONSE: feed not valid JSON array (retryable=False)",
        ),
        ("COL_TIMEOUT", "total deadline exceeded", True, "COL_TIMEOUT: total deadline exceeded (retryable=True)"),
    ],
    ids=["fetch_retryable", "response_not_retryable", "timeout_retryable"],
)
def test_collector_error_message_shape(
    code: str,
    reason: str,
    retryable: bool,
    expected: str,
) -> None:
    message = collector_error_message(code=code, reason=reason, retryable=retryable)
    assert message == expected
    assert code in message
    assert reason in message
    assert f"(retryable={retryable})" in message


@pytest.mark.parametrize(
    ("reason_code", "stage", "field", "expected"),
    [
        (
            RejectionReason.VALIDATION_FAILED,
            "deleted_story",
            None,
            "validation failed at deleted_story",
        ),
        (
            RejectionReason.VALIDATION_FAILED,
            "required_fields",
            "title",
            "validation failed at required_fields: title",
        ),
        (
            RejectionReason.NORMALIZATION_FAILED,
            "json_decode",
            None,
            "normalization failed at json_decode",
        ),
        (
            RejectionReason.NORMALIZATION_FAILED,
            "url",
            None,
            "normalization failed at url",
        ),
        (
            RejectionReason.DUPLICATE,
            None,
            None,
            "duplicate source_id in feed order",
        ),
        (
            RejectionReason.UNTRUSTED_CONTENT,
            None,
            None,
            "untrusted control characters in content",
        ),
    ],
    ids=[
        "validation_deleted_story",
        "validation_required_field",
        "normalization_json_decode",
        "normalization_url",
        "duplicate",
        "untrusted_content",
    ],
)
def test_rejection_detail_templates(
    reason_code: RejectionReason,
    stage: str | None,
    field: str | None,
    expected: str,
) -> None:
    detail = rejection_detail(reason_code=reason_code, stage=stage, field=field)
    assert detail == expected
    assert len(detail) <= ERROR_DETAIL_MAX_LENGTH


def test_rejection_detail_truncates_long_stage() -> None:
    long_stage = "x" * 300
    detail = rejection_detail(
        reason_code=RejectionReason.NORMALIZATION_FAILED,
        stage=long_stage,
    )
    assert len(detail) == ERROR_DETAIL_MAX_LENGTH
    assert detail == f"normalization failed at {long_stage}"[:ERROR_DETAIL_MAX_LENGTH]


def test_messages_never_interpolate_raw_body_bytes() -> None:
    body_text = _FAKE_RAW_BODY.decode()
    fetch_message = collector_error_message(
        code="COL_RESPONSE",
        reason="invalid JSON",
        retryable=False,
    )
    json_rejection = rejection_detail(
        reason_code=RejectionReason.NORMALIZATION_FAILED,
        stage="json_decode",
    )

    assert body_text not in fetch_message
    assert _FAKE_RAW_BODY not in fetch_message.encode()
    assert body_text not in json_rejection
