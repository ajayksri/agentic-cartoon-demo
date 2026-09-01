"""Unit tests for runtime.constants (RT-001)."""

from __future__ import annotations

from config.types import TaskType

from runtime.constants import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_WORKER_ROLE,
    METRIC_BOOTSTRAP_FAILURES,
    OUTBOX_RETRY_MAX_ATTEMPTS,
    OUTBOX_RETRY_MAX_SECONDS,
    PROBE_NAME_POSTGRES,
    PROBE_NAME_REDIS,
    SCRIPT_API,
    WORKER_GROUP_BY_TASK_TYPE,
    WORKER_STREAM_BY_TASK_TYPE,
)


def test_worker_stream_map_matches_task_queue_conventions() -> None:
    assert WORKER_STREAM_BY_TASK_TYPE[TaskType.COLLECT] == "cartoon:tasks:collect"
    assert WORKER_STREAM_BY_TASK_TYPE[TaskType.SELECT_TOPIC] == "cartoon:tasks:select_topic"
    assert WORKER_GROUP_BY_TASK_TYPE[TaskType.REVIEW_SCENARIO] == "cartoon:workers:review_scenario"
    assert set(WORKER_STREAM_BY_TASK_TYPE) == set(TaskType)


def test_default_worker_role_is_collect() -> None:
    assert DEFAULT_WORKER_ROLE is TaskType.COLLECT


def test_outbox_retry_and_metric_constants() -> None:
    assert OUTBOX_RETRY_MAX_ATTEMPTS == 5
    assert OUTBOX_RETRY_MAX_SECONDS == 30.0
    assert METRIC_BOOTSTRAP_FAILURES == "runtime_bootstrap_failures_total"


def test_api_and_probe_defaults() -> None:
    assert DEFAULT_API_HOST == "0.0.0.0"
    assert DEFAULT_API_PORT == 8000
    assert PROBE_NAME_POSTGRES == "postgres"
    assert PROBE_NAME_REDIS == "redis"
    assert SCRIPT_API == "cartoon-demo-api"
