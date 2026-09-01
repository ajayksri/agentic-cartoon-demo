"""Shared contract-test fixtures for task_queue module (TQ-010, LLD §9.4)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import pytest

from task_queue import TaskMessage, TaskQueue

from .helpers import COLLECT_STREAM, minimal_task_message


def redis_url() -> str:
    """Read REDIS_URL or default local Redis URL."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def seed_consumer_group(queue: TaskQueue, stream: str, group: str) -> None:
    """Bootstrap consumer group via public ensure_consumer_group."""
    queue.ensure_consumer_group(stream, group)


def _redis_available(url: str) -> bool:
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


def _test_app_config(redis_url_str: str) -> Any:
    """Minimal AppConfig-like object for create_task_queue contract tests."""
    from config.types import InfrastructureConfig, RedisConfig

    parsed = urlparse(redis_url_str)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int((parsed.path or "/0").lstrip("/") or "0")

    return type(
        "TestAppConfig",
        (),
        {
            "infrastructure": InfrastructureConfig(
                postgres=type("Pg", (), {})(),  # type: ignore[arg-type]
                redis=RedisConfig(
                    host=host,
                    port=port,
                    db=db,
                    password_env=None,
                ),
            ),
            "resolve_credential": lambda self, env_var_name: None,
        },
    )()


def _flush_test_stream(url: str, stream: str) -> None:
    try:
        import redis

        client = redis.Redis.from_url(url)
        client.delete(stream)
    except Exception:
        pass


@pytest.fixture
def redis_url_fixture() -> str:
    return redis_url()


@pytest.fixture
def minimal_task_message_fixture() -> Callable[..., TaskMessage]:
    return minimal_task_message


@pytest.fixture
def seed_consumer_group_fixture() -> Callable[[TaskQueue, str, str], None]:
    return seed_consumer_group


@pytest.fixture
def task_queue_instance() -> TaskQueue:
    """create_task_queue against configured Redis; flush test streams in teardown."""
    url = redis_url()
    if not _redis_available(url):
        pytest.skip("Redis not available")

    from task_queue import create_task_queue

    config = _test_app_config(url)
    queue = create_task_queue(config)
    yield queue
    if hasattr(queue, "close"):
        queue.close()  # type: ignore[attr-defined]
    _flush_test_stream(url, COLLECT_STREAM)
