"""Sync/async bridge for ApiClient coroutines."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from .errors import CliError, map_to_connection_error

T = TypeVar("T")


class AsyncRunner:
    """Runs async ApiClient coroutines from sync handler context."""

    def __init__(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            if self._loop is not None:
                return self._loop.run_until_complete(coro)
            return asyncio.run(coro)
        except CliError:
            raise
        except Exception as exc:
            raise map_to_connection_error(exc) from exc
