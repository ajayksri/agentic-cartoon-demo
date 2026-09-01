"""Redis connection pool lifecycle (LLD §3.5)."""

from __future__ import annotations

from dataclasses import dataclass

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError

from config.types import AppConfig

from .errors import TaskQueueConnectionError, TaskQueueUnavailableError
from .messages import connection_message, unavailable_message

DEFAULT_SOCKET_CONNECT_TIMEOUT = 5.0
DEFAULT_SOCKET_TIMEOUT = 30.0
DEFAULT_MAX_CONNECTIONS = 10


@dataclass(frozen=True, slots=True)
class RedisConnectionParams:
    host: str
    port: int
    db: int
    password: str | None
    socket_connect_timeout: float = DEFAULT_SOCKET_CONNECT_TIMEOUT
    socket_timeout: float = DEFAULT_SOCKET_TIMEOUT
    max_connections: int = DEFAULT_MAX_CONNECTIONS
    ssl: bool = False


class RedisConnectionManager:
    def __init__(self, params: RedisConnectionParams) -> None:
        self._params = params
        self._client: redis.Redis | None = None
        self._closed = False

    @classmethod
    def from_app_config(cls, config: AppConfig) -> RedisConnectionManager:
        redis_cfg = config.infrastructure.redis
        password: str | None = None
        if redis_cfg.password_env is not None:
            password = config.resolve_credential(redis_cfg.password_env)

        params = RedisConnectionParams(
            host=redis_cfg.host,
            port=redis_cfg.port,
            db=redis_cfg.db,
            password=password,
        )
        return cls(params)

    def connect(self) -> redis.Redis:
        try:
            pool = redis.ConnectionPool(
                host=self._params.host,
                port=self._params.port,
                db=self._params.db,
                password=self._params.password,
                socket_connect_timeout=self._params.socket_connect_timeout,
                socket_timeout=self._params.socket_timeout,
                max_connections=self._params.max_connections,
                decode_responses=True,
            )
            client = redis.Redis(connection_pool=pool)
            client.ping()
            self._client = client
            self._closed = False
            return client
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise TaskQueueConnectionError(
                connection_message(
                    host=self._params.host,
                    port=self._params.port,
                    reason=str(exc),
                ),
            ) from exc

    def client(self) -> redis.Redis:
        if self._client is None:
            raise TaskQueueConnectionError(
                connection_message(
                    host=self._params.host,
                    port=self._params.port,
                    reason="not connected",
                ),
            )
        return self._client

    def close(self) -> None:
        if self._client is None or self._closed:
            return
        pool = self._client.connection_pool
        pool.disconnect()
        self._closed = True
        self._client = None

    def ping(self) -> None:
        client = self.client()
        try:
            client.ping()
        except (RedisTimeoutError, TimeoutError) as exc:
            raise TaskQueueUnavailableError(
                unavailable_message(operation="ping", reason=str(exc)),
            ) from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise TaskQueueConnectionError(
                connection_message(
                    host=self._params.host,
                    port=self._params.port,
                    reason=str(exc),
                ),
            ) from exc
