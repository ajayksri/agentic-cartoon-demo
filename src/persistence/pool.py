"""Bounded psycopg connection pool lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg_pool.errors import PoolTimeout

from persistence.bootstrap import ConnectionSettings
from persistence.errors import PersistenceConnectionError


def _configure_connection(connection: psycopg.Connection) -> None:
    """Return dict rows from fetchone/fetchall (persistence LLD §3.1)."""
    connection.row_factory = dict_row


class ConnectionPoolManager:
    def __init__(self, settings: ConnectionSettings) -> None:
        self._settings = settings
        conninfo = make_conninfo(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
        )
        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=settings.min_pool_size,
            max_size=settings.max_pool_size,
            timeout=settings.connection_timeout_seconds,
            configure=_configure_connection,
            open=True,
        )

    @contextmanager
    def acquire(self) -> Iterator[psycopg.Connection]:
        try:
            with self._pool.connection(
                timeout=self._settings.connection_timeout_seconds
            ) as connection:
                yield connection
        except (TimeoutError, PoolTimeout) as exc:
            raise PersistenceConnectionError(
                "Persistence connection error during acquire"
            ) from exc

    def health_check(self) -> None:
        try:
            with self._pool.connection(
                timeout=self._settings.connection_timeout_seconds
            ) as connection:
                connection.execute("SELECT 1")
        except Exception as exc:
            raise PersistenceConnectionError(
                "Persistence connection error during health_check"
            ) from exc

    def close(self) -> None:
        self._pool.close()
