"""In-memory transaction manager for contract and unit tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from persistence.errors import PersistenceTransactionError


class InMemoryTransactionManager:
    """Mirrors PostgresTransactionManager session scoping via contextvars."""

    def __init__(self) -> None:
        self._in_transaction: ContextVar[bool] = ContextVar(
            "in_memory_txn",
            default=False,
        )
        self._snapshot_fns: list[Callable[[], Any]] = []
        self._restore_fns: list[Callable[[Any], None]] = []

    def register_store(
        self,
        snapshot_fn: Callable[[], Any],
        restore_fn: Callable[[Any], None],
    ) -> None:
        self._snapshot_fns.append(snapshot_fn)
        self._restore_fns.append(restore_fn)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._in_transaction.get():
            raise PersistenceTransactionError("Nested transaction not supported")

        snapshots = [fn() for fn in self._snapshot_fns]
        token: Token[bool] = self._in_transaction.set(True)
        try:
            try:
                yield
            except Exception:
                for restore_fn, snapshot in zip(
                    self._restore_fns,
                    snapshots,
                    strict=True,
                ):
                    restore_fn(snapshot)
                raise
        finally:
            self._in_transaction.reset(token)

    def is_in_transaction(self) -> bool:
        return self._in_transaction.get()
