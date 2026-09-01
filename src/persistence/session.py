"""Active-session contextvar binding for borrowed connections."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

import psycopg

_active_session: ContextVar[SessionScope | None] = ContextVar(
    "persistence_active_session",
    default=None,
)


@dataclass
class SessionScope:
    """One borrowed connection; optionally inside an open transaction."""

    connection: psycopg.Connection
    in_transaction: bool = False


def get_active_session() -> SessionScope | None:
    return _active_session.get()


def set_active_session(scope: SessionScope | None) -> Token[SessionScope | None]:
    return _active_session.set(scope)
