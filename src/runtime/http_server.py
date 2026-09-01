"""API HTTP host and transaction-scoped mutating routes (LLD §10)."""

from __future__ import annotations

import functools
import threading
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import FastAPI
from persistence.protocols import TransactionManager

from .settings import ApiServerConfig
from .shutdown import ShutdownState

T = TypeVar("T")


class TransactionMutatingContext:
    """Wraps mutating API handlers in a persistence transaction scope."""

    def __init__(self, transaction_manager: TransactionManager) -> None:
        self._transaction_manager = transaction_manager

    def wrap_mutating(
        self,
        handler: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @functools.wraps(handler)
        async def wrapped(*args: object, **kwargs: object) -> T:
            with self._transaction_manager.transaction():
                return await handler(*args, **kwargs)

        return wrapped


def _request_server_stop(server: object) -> None:
    """Signal Uvicorn to exit (Event API pre-0.52; bool attribute in newer releases)."""
    should_exit = getattr(server, "should_exit", None)
    if should_exit is None:
        return
    if callable(getattr(should_exit, "set", None)):
        should_exit.set()
        return
    try:
        server.should_exit = True  # type: ignore[attr-defined]
    except AttributeError:
        return


def _register_shutdown_hooks(
    shutdown: ShutdownState,
    *,
    on_stop: Callable[[], None],
) -> None:
    """Signal Uvicorn to exit when process shutdown is requested."""

    def _watch() -> None:
        shutdown.requested.wait()
        on_stop()

    threading.Thread(
        target=_watch,
        daemon=True,
        name="api-http-shutdown-watcher",
    ).start()


class ApiHttpServer:
    """FastAPI + Uvicorn host for the API process entry."""

    def __init__(
        self,
        *,
        server_factory: Callable[..., object] | None = None,
        app_factory: Callable[[], FastAPI] | None = None,
    ) -> None:
        self._server_factory = server_factory or _default_server_factory
        self._app_factory = app_factory or FastAPI

    def serve(
        self,
        *,
        router: object,
        config: ApiServerConfig,
        shutdown: ShutdownState,
    ) -> None:
        app = self._app_factory()
        app.include_router(router)  # type: ignore[arg-type]
        server = self._server_factory(
            app,
            host=config.host,
            port=config.port,
            timeout_graceful_shutdown=config.graceful_shutdown_seconds,
        )
        _register_shutdown_hooks(
            shutdown,
            on_stop=lambda: _request_server_stop(server),
        )
        server.run()  # type: ignore[attr-defined]


def _default_server_factory(
    app: FastAPI,
    *,
    host: str,
    port: int,
    timeout_graceful_shutdown: float,
) -> object:
    from uvicorn import Config, Server

    uvicorn_config = Config(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
    )
    return Server(uvicorn_config)
