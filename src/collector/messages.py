"""Error and rejection message templates for the collector module."""

from __future__ import annotations

from collector.constants import ERROR_DETAIL_MAX_LENGTH
from collector.types import RejectionReason


def collector_error_message(*, code: str, reason: str, retryable: bool) -> str:
    return f"{code}: {reason} (retryable={retryable})"


def rejection_detail(
    *,
    reason_code: RejectionReason,
    stage: str | None = None,
    field: str | None = None,
) -> str:
    if reason_code is RejectionReason.VALIDATION_FAILED:
        if stage is not None and field is not None:
            message = f"validation failed at {stage}: {field}"
        elif stage is not None:
            message = f"validation failed at {stage}"
        else:
            message = "validation failed"
    elif reason_code is RejectionReason.NORMALIZATION_FAILED:
        message = (
            f"normalization failed at {stage}"
            if stage is not None
            else "normalization failed"
        )
    elif reason_code is RejectionReason.DUPLICATE:
        message = "duplicate source_id in feed order"
    elif reason_code is RejectionReason.UNTRUSTED_CONTENT:
        message = "untrusted control characters in content"
    else:
        message = str(reason_code)

    return message[:ERROR_DETAIL_MAX_LENGTH]
