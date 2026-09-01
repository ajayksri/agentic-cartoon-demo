"""Fake transaction manager with is_in_transaction probe."""

from __future__ import annotations

from dataclasses import dataclass

from persistence.errors import PersistenceTransactionError


@dataclass
class FakeTransactionManager:
    """Tracks transaction commit for WKR-TC-070."""

    _active: bool = False
    commits: int = 0

    def is_in_transaction(self) -> bool:
        return self._active

    def transaction(self) -> "_TxnScope":
        return _TxnScope(self)


class _TxnScope:
    def __init__(self, manager: FakeTransactionManager) -> None:
        self._manager = manager

    def __enter__(self) -> "_TxnScope":
        if self._manager._active:
            raise PersistenceTransactionError("Nested transaction not supported")
        self._manager._active = True
        return self

    def __exit__(self, *_args: object) -> None:
        self._manager._active = False
        self._manager.commits += 1
