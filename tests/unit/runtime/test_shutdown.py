"""Unit tests for RT-009 — ShutdownCoordinator."""

from __future__ import annotations

import threading

import pytest

from runtime import WORKER_ENTRY
from runtime.errors import ProcessShutdownError
from runtime.shutdown import ShutdownCoordinator, ShutdownState


def test_signal_handler_sets_shutdown_event() -> None:
    handlers: dict[int, object] = {}

    def registrar(signum: int, handler: object) -> None:
        handlers[signum] = handler

    state = ShutdownCoordinator.register(
        WORKER_ENTRY,
        grace_seconds=1.0,
        signal_registrar=registrar,
    )

    assert isinstance(state, ShutdownState)
    assert not state.requested.is_set()
    for handler in handlers.values():
        handler(None, None)  # type: ignore[operator]
    assert state.requested.is_set()


def test_join_with_grace_raises_when_thread_still_alive() -> None:
    started = threading.Event()

    def worker() -> None:
        started.set()
        threading.Event().wait()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    started.wait(timeout=1.0)

    with pytest.raises(ProcessShutdownError) as exc_info:
        ShutdownCoordinator.join_with_grace(
            thread,
            grace_seconds=0.05,
            entry=WORKER_ENTRY,
        )

    assert exc_info.value.entry == WORKER_ENTRY
    assert "grace_seconds" in str(exc_info.value)


def test_shutdown_request_is_idempotent() -> None:
    state = ShutdownState(
        requested=threading.Event(),
        grace_seconds=5.0,
        process_kind=WORKER_ENTRY.kind,
        service_name=WORKER_ENTRY.service_name,
    )

    state.requested.set()
    state.requested.set()

    assert state.requested.is_set()
