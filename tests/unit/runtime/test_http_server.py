"""Unit tests for RT-011 — ApiHttpServer / TransactionMutatingContext (LLD §10)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from runtime import ProcessKind

_LLD_DEFAULT_HOST = "0.0.0.0"
_LLD_DEFAULT_PORT = 8000
_LLD_DEFAULT_GRACE = 30.0


def test_wrap_mutating_opens_and_closes_transaction() -> None:
    """CG-RT-HLD-001: mutating wrapper uses transaction_manager.transaction()."""
    from runtime.http_server import TransactionMutatingContext

    txn = MagicMock()
    ctx_manager = MagicMock()
    ctx_manager.__enter__ = MagicMock(return_value=None)
    ctx_manager.__exit__ = MagicMock(return_value=False)
    txn.transaction.return_value = ctx_manager

    wrapper = TransactionMutatingContext(transaction_manager=txn)

    async def handler() -> str:
        return "ok"

    wrapped = wrapper.wrap_mutating(handler)
    result = asyncio.run(wrapped())

    assert result == "ok"
    txn.transaction.assert_called_once()
    ctx_manager.__enter__.assert_called_once()
    ctx_manager.__exit__.assert_called_once()


def test_api_server_config_defaults_match_constants() -> None:
    """LLD §4.2 / §10.3: ApiServerConfig defaults from RT-001 constants."""
    from runtime.settings import ApiServerConfig

    config = ApiServerConfig()

    assert config.host == _LLD_DEFAULT_HOST
    assert config.port == _LLD_DEFAULT_PORT
    assert config.graceful_shutdown_seconds == _LLD_DEFAULT_GRACE


def test_api_http_server_accepts_router_and_shutdown_state() -> None:
    """LLD §10.3: serve() accepts router + shutdown without starting live HTTP in unit tests."""
    from fastapi import APIRouter

    from runtime.http_server import ApiHttpServer
    from runtime.settings import ApiServerConfig
    from runtime.shutdown import ShutdownState

    server = ApiHttpServer(server_factory=_NoOpUvicornServer)
    shutdown = ShutdownState(
        requested=__import__("threading").Event(),
        grace_seconds=_LLD_DEFAULT_GRACE,
        process_kind=ProcessKind.API,
        service_name="cartoon-demo-api",
    )

    server.serve(
        router=APIRouter(),
        config=ApiServerConfig(),
        shutdown=shutdown,
    )


class _NoOpUvicornServer:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.should_exit = __import__("threading").Event()

    def run(self) -> None:
        return None
