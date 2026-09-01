"""Pre-code test mold for TQ-006 — RedisConnectionManager (LLD §3.5)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config.errors import ConfigCredentialMissingError
from config.types import InfrastructureConfig, RedisConfig
from task_queue import TaskQueueConnectionError, TaskQueueUnavailableError


def _redis_config(**overrides: object) -> RedisConfig:
    defaults: dict[str, object] = {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "password_env": None,
    }
    defaults.update(overrides)
    return RedisConfig(**defaults)  # type: ignore[arg-type]


def _app_config(redis: RedisConfig) -> SimpleNamespace:
    return SimpleNamespace(
        infrastructure=InfrastructureConfig(
            postgres=MagicMock(),
            redis=redis,
        ),
        resolve_credential=MagicMock(return_value=None),
    )


def test_from_app_config_reads_infrastructure_redis() -> None:
    """from_app_config builds manager from AppConfig.infrastructure.redis."""
    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    config = _app_config(_redis_config(host="redis.internal", port=6380, db=2))
    manager = RedisConnectionManager.from_app_config(config)  # type: ignore[arg-type]

    assert isinstance(manager, RedisConnectionManager)
    params = manager._params  # type: ignore[attr-defined]
    assert isinstance(params, RedisConnectionParams)
    assert params.host == "redis.internal"
    assert params.port == 6380
    assert params.db == 2


def test_from_app_config_propagates_config_credential_missing_error() -> None:
    """ConfigCredentialMissingError propagates without translation."""
    from task_queue.connection import RedisConnectionManager

    config = _app_config(_redis_config(password_env="REDIS_PASSWORD"))
    config.resolve_credential.side_effect = ConfigCredentialMissingError(
        "missing credential",
        env_var_name="REDIS_PASSWORD",
    )

    with pytest.raises(ConfigCredentialMissingError):
        RedisConnectionManager.from_app_config(config)  # type: ignore[arg-type]


def test_connect_success_returns_redis_client() -> None:
    """connect creates pool, Redis client, and PING succeeds."""
    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    with patch("task_queue.connection.redis.Redis") as redis_cls:
        client = MagicMock()
        redis_cls.return_value = client
        manager = RedisConnectionManager(
            RedisConnectionParams(host="localhost", port=6379, db=0, password=None)
        )

        connected = manager.connect()

        assert connected is client
        client.ping.assert_called_once()


def test_connect_failure_raises_task_queue_connection_error_without_password() -> None:
    """Connection failure raises TaskQueueConnectionError without password in message."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    secret = "super-secret-redis-password"
    with patch("task_queue.connection.redis.Redis") as redis_cls:
        redis_cls.return_value.ping.side_effect = RedisConnectionError("auth failed")
        manager = RedisConnectionManager(
            RedisConnectionParams(
                host="localhost",
                port=6379,
                db=0,
                password=secret,
            )
        )

        with pytest.raises(TaskQueueConnectionError) as exc_info:
            manager.connect()

        assert exc_info.value.code == "TQ_CONN"
        assert secret not in str(exc_info.value)


def test_client_raises_when_not_connected() -> None:
    """client() raises TaskQueueConnectionError when connect was not called."""
    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    manager = RedisConnectionManager(
        RedisConnectionParams(host="localhost", port=6379, db=0, password=None)
    )

    with pytest.raises(TaskQueueConnectionError):
        manager.client()


def test_close_is_idempotent() -> None:
    """close() may be called multiple times without error."""
    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    with patch("task_queue.connection.redis.Redis") as redis_cls:
        client = MagicMock()
        pool = MagicMock()
        client.connection_pool = pool
        redis_cls.return_value = client
        manager = RedisConnectionManager(
            RedisConnectionParams(host="localhost", port=6379, db=0, password=None)
        )
        manager.connect()

        manager.close()
        manager.close()

        pool.disconnect.assert_called()


def test_ping_timeout_raises_task_queue_unavailable_error() -> None:
    """ping timeout maps to TaskQueueUnavailableError."""
    from task_queue.connection import RedisConnectionManager, RedisConnectionParams

    with patch("task_queue.connection.redis.Redis") as redis_cls:
        client = MagicMock()
        client.ping.side_effect = [None, TimeoutError("timed out")]
        redis_cls.return_value = client
        manager = RedisConnectionManager(
            RedisConnectionParams(host="localhost", port=6379, db=0, password=None)
        )
        manager.connect()

        with pytest.raises(TaskQueueUnavailableError) as exc_info:
            manager.ping()

        assert exc_info.value.code == "TQ_UNAVAILABLE"


def test_connect_uses_decode_responses_and_max_connections() -> None:
    """connect creates ConnectionPool with decode_responses=True and max_connections=10."""
    from task_queue.connection import (
        DEFAULT_MAX_CONNECTIONS,
        RedisConnectionManager,
        RedisConnectionParams,
    )

    with patch("task_queue.connection.redis.ConnectionPool") as pool_cls, patch(
        "task_queue.connection.redis.Redis"
    ) as redis_cls:
        client = MagicMock()
        redis_cls.return_value = client
        manager = RedisConnectionManager(
            RedisConnectionParams(host="localhost", port=6379, db=0, password=None)
        )

        manager.connect()

        pool_cls.assert_called_once()
        kwargs = pool_cls.call_args.kwargs
        assert kwargs["decode_responses"] is True
        assert kwargs["max_connections"] == DEFAULT_MAX_CONNECTIONS
