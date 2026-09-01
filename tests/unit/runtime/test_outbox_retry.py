"""Unit tests for RT-007 — outbox retry helpers (LLD §11.3, CG-RT-007)."""

from __future__ import annotations

import pytest

from runtime.constants import OUTBOX_RETRY_MAX_ATTEMPTS, OUTBOX_RETRY_MAX_SECONDS
from runtime.outbox import OutboxPublishFrame, _enqueue_with_retry, _mark_published_with_retry, outbox_retry_schedule

_LLD_MAX_ATTEMPTS = 5
_LLD_MAX_SECONDS = 30.0
_LLD_INITIAL_SECONDS = 1.0


def test_retry_policy_max_attempts_is_five() -> None:
    """CG-RT-007: OUTBOX_RETRY_MAX_ATTEMPTS == 5."""
    from runtime.constants import OUTBOX_RETRY_MAX_ATTEMPTS as constant_attempts

    schedule = outbox_retry_schedule(
        initial_seconds=_LLD_INITIAL_SECONDS,
        max_seconds=_LLD_MAX_SECONDS,
        max_attempts=_LLD_MAX_ATTEMPTS,
    )

    assert len(schedule) == _LLD_MAX_ATTEMPTS
    assert constant_attempts == _LLD_MAX_ATTEMPTS


def test_retry_backoff_caps_at_thirty_seconds() -> None:
    """CG-RT-007: backoff capped at OUTBOX_RETRY_MAX_SECONDS."""
    schedule = outbox_retry_schedule(
        initial_seconds=_LLD_INITIAL_SECONDS,
        max_seconds=_LLD_MAX_SECONDS,
        max_attempts=_LLD_MAX_ATTEMPTS,
    )

    assert max(schedule) <= _LLD_MAX_SECONDS


def test_enqueue_retry_does_not_mark_published_on_failure() -> None:
    """MOD-RT-INV-014: mark_published must not run when enqueue fails."""
    frame = OutboxPublishFrame(entry=object(), stream="cartoon:tasks:collect")  # type: ignore[arg-type]
    frame.message = object()  # type: ignore[assignment]
    repo = _RecordingOutboxRepo()
    queue = _FailingQueue()

    with pytest.raises(Exception):
        _enqueue_with_retry(frame, queue=queue, outbox_repo=repo)

    assert repo.mark_calls == []


def test_mark_published_retry_reuses_same_backoff_policy() -> None:
    """LLD §11.3: mark_published retry uses same bounds as enqueue."""
    repo = _FlakyMarkRepo(failures=OUTBOX_RETRY_MAX_ATTEMPTS - 1)
    frame = OutboxPublishFrame(entry=_OutboxEntryStub(), stream="cartoon:tasks:collect")

    _mark_published_with_retry(frame, repo=repo, max_seconds=OUTBOX_RETRY_MAX_SECONDS)

    assert repo.attempts == OUTBOX_RETRY_MAX_ATTEMPTS


class _OutboxEntryStub:
    outbox_id = "ob-1"


class _RecordingOutboxRepo:
    def __init__(self) -> None:
        self.mark_calls: list[object] = []

    def mark_published(self, outbox_id: str, *, published_at: object) -> None:
        self.mark_calls.append((outbox_id, published_at))


class _FailingQueue:
    def enqueue(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("queue unavailable")


class _FlakyMarkRepo:
    def __init__(self, *, failures: int) -> None:
        self._failures = failures
        self.attempts = 0

    def mark_published(self, _outbox_id: str, *, published_at: object) -> None:
        del published_at
        self.attempts += 1
        if self.attempts <= self._failures:
            raise RuntimeError("transient mark failure")
