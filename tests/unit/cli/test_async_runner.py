"""Unit tests for async runner."""

from __future__ import annotations

import asyncio

import pytest

from cli.async_runner import AsyncRunner
from cli.errors import CliConnectionError, CliUsageError


async def _success() -> str:
    return "ok"


async def _raise_usage() -> None:
    raise CliUsageError("bad")


async def _raise_runtime() -> None:
    raise RuntimeError("boom")


def test_async_runner_returns_result() -> None:
    assert AsyncRunner().run(_success()) == "ok"


def test_async_runner_reraises_cli_error() -> None:
    with pytest.raises(CliUsageError):
        AsyncRunner().run(_raise_usage())


def test_async_runner_maps_unexpected_to_connection_error() -> None:
    with pytest.raises(CliConnectionError):
        AsyncRunner().run(_raise_runtime())


def test_async_runner_uses_injected_loop() -> None:
    loop = asyncio.new_event_loop()
    try:
        runner = AsyncRunner(loop=loop)
        assert runner.run(_success()) == "ok"
    finally:
        loop.close()
