"""Unit tests for WKR-001 constants (LLD §3)."""

from __future__ import annotations

from config.types import TaskType

from worker.constants import (
    AGENT_STAGE_TYPES,
    ARTIFACT_SCHEMA_V1,
    ARTIFACT_SCHEMA_VERSION,
    COLLECT_CONCURRENCY_LIMIT,
    DEFAULT_LEASE_RENEW_INTERVAL_SECONDS,
    DEFAULT_LEASE_TTL_SECONDS,
    DEFAULT_SHUTDOWN_GRACE_SECONDS,
    FORBIDDEN_LOG_FIELDS,
    IDEMPOTENCY_KEY_FORMAT,
    LOGICAL_VERSION_FIXED_TYPES,
    METRIC_DUPLICATE,
    METRIC_EXECUTION,
    METRIC_FAILURE,
    METRIC_QUEUE_WAIT,
    METRIC_RETRY,
)


def test_idempotency_key_format() -> None:
    assert IDEMPOTENCY_KEY_FORMAT == "{workflow_id}:{task_type}:{logical_version}"


def test_lease_defaults() -> None:
    assert DEFAULT_LEASE_TTL_SECONDS == 60
    assert DEFAULT_LEASE_RENEW_INTERVAL_SECONDS == 30


def test_concurrency_and_shutdown_defaults() -> None:
    assert COLLECT_CONCURRENCY_LIMIT == 1
    assert DEFAULT_SHUTDOWN_GRACE_SECONDS == 30.0


def test_logical_version_fixed_types() -> None:
    assert TaskType.COLLECT in LOGICAL_VERSION_FIXED_TYPES
    assert TaskType.SELECT_TOPIC in LOGICAL_VERSION_FIXED_TYPES
    assert TaskType.GENERATE_SCENARIO not in LOGICAL_VERSION_FIXED_TYPES


def test_metric_names() -> None:
    assert METRIC_QUEUE_WAIT == "worker_task_queue_wait_duration_ms"
    assert METRIC_EXECUTION == "worker_task_execution_duration_ms"
    assert METRIC_DUPLICATE == "worker_duplicate_total"
    assert METRIC_RETRY == "worker_retry_total"
    assert METRIC_FAILURE == "worker_task_failure_total"


def test_forbidden_log_fields() -> None:
    expected = frozenset(
        {
            "prompt",
            "prompt_text",
            "response",
            "content",
            "api_key",
            "artifact_body",
        }
    )
    assert FORBIDDEN_LOG_FIELDS == expected


def test_artifact_schema_constants() -> None:
    assert ARTIFACT_SCHEMA_VERSION == "schema_version"
    assert ARTIFACT_SCHEMA_V1 == 1


def test_agent_stage_types() -> None:
    assert TaskType.SELECT_TOPIC in AGENT_STAGE_TYPES
    assert TaskType.GENERATE_SCENARIO in AGENT_STAGE_TYPES
    assert TaskType.REVIEW_SCENARIO in AGENT_STAGE_TYPES
    assert TaskType.COLLECT not in AGENT_STAGE_TYPES
