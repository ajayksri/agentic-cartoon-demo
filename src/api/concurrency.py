"""Async helpers for invoking blocking workflow engine calls."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def _run_sync(callable: Callable[[], T]) -> T:
    """Invoke blocking WorkflowEngine method without blocking the event loop."""
    return await asyncio.to_thread(callable)
