"""Process shutdown coordination — signals and grace joins (LLD §14)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Graceful shutdown — SIGTERM/SIGINT with grace period
# lets in-flight tasks finish before exit, avoiding duplicate delivery on restart.

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .errors import ProcessShutdownError
from .messages import shutdown_grace_message
from .types import ProcessEntryPoint, ProcessKind

SignalRegistrar = Callable[[int, Callable[..., None]], object]


@dataclass
class ShutdownState:
    """Shared shutdown request state for runners and HTTP host."""

    requested: threading.Event
    grace_seconds: float
    process_kind: ProcessKind
    service_name: str


class ShutdownCoordinator:
    """Registers SIGTERM/SIGINT and provides grace join helpers."""

    @staticmethod
    def register(
        entry: ProcessEntryPoint,
        *,
        grace_seconds: float,
        signal_registrar: SignalRegistrar | None = None,
    ) -> ShutdownState:
        state = ShutdownState(
            requested=threading.Event(),
            grace_seconds=grace_seconds,
            process_kind=entry.kind,
            service_name=entry.service_name,
        )

        def _request_shutdown(*_args: object, **_kwargs: object) -> None:
            state.requested.set()

        registrar = signal_registrar or signal.signal
        registrar(signal.SIGTERM, _request_shutdown)
        registrar(signal.SIGINT, _request_shutdown)
        return state

    @staticmethod
    def wait_for_signal(state: ShutdownState) -> None:
        state.requested.wait()

    @staticmethod
    def join_with_grace(
        thread: threading.Thread,
        *,
        grace_seconds: float,
        entry: ProcessEntryPoint,
    ) -> None:
        thread.join(timeout=grace_seconds)
        if thread.is_alive():
            raise ProcessShutdownError(
                shutdown_grace_message(kind=entry.kind, grace_seconds=grace_seconds),
                entry=entry,
            )
