"""In-memory transaction manager for workflow contract tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token


class FakeTransactionManager:
    """Context manager with is_in_transaction() probe (LLD §6, §14)."""

    def __init__(self) -> None:
        self._in_transaction: ContextVar[bool] = ContextVar(
            "workflow_fake_txn",
            default=False,
        )
        self._depth: ContextVar[int] = ContextVar("workflow_fake_txn_depth", default=0)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        depth = self._depth.get()
        token_depth: Token[int] = self._depth.set(depth + 1)
        token_txn: Token[bool] = self._in_transaction.set(True)
        try:
            yield
        finally:
            self._depth.reset(token_depth)
            if depth == 0:
                self._in_transaction.reset(token_txn)

    def is_in_transaction(self) -> bool:
        return self._in_transaction.get()
