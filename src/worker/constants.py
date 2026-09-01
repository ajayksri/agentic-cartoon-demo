"""Worker module constants and defaults (LLD §3)."""

from __future__ import annotations

from config.types import TaskType

# Idempotency (CG-WKR-001)
IDEMPOTENCY_KEY_FORMAT = "{workflow_id}:{task_type}:{logical_version}"

# Leases (CG-WKR-002)
DEFAULT_LEASE_TTL_SECONDS: int = 60
DEFAULT_LEASE_RENEW_INTERVAL_SECONDS: int = 30

# Concurrency (CG-WKR-HLD-003)
COLLECT_CONCURRENCY_LIMIT: int = 1

# Shutdown (CG-WKR-009)
DEFAULT_SHUTDOWN_GRACE_SECONDS: float = 30.0

# Logical version defaults per task type (workflow LLD §10)
LOGICAL_VERSION_FIXED_TYPES: frozenset[TaskType] = frozenset(
    {
        TaskType.COLLECT,
        TaskType.SELECT_TOPIC,
    }
)

# Telemetry logical metric names (CG-WKR-004)
METRIC_QUEUE_WAIT = "worker_task_queue_wait_duration_ms"
METRIC_EXECUTION = "worker_task_execution_duration_ms"
METRIC_DUPLICATE = "worker_duplicate_total"
METRIC_RETRY = "worker_retry_total"
METRIC_FAILURE = "worker_task_failure_total"

# Span / log event names
SPAN_HANDLE_TASK = "worker.handle_task"
LOG_TASK_STARTED = "task_started"
LOG_TASK_COMPLETED = "task_completed"
LOG_TASK_FAILED = "task_failed"
LOG_DUPLICATE = "duplicate_detected"
LOG_RETRY = "retry_scheduled"
LOG_STALE = "stale_task_ignored"
LOG_LEASE_CONFLICT = "lease_conflict"

# Forbidden log field keys (MOD-WKR-INV-022)
FORBIDDEN_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "prompt",
        "prompt_text",
        "response",
        "content",
        "api_key",
        "artifact_body",
    }
)

# Artifact content schema version keys
ARTIFACT_SCHEMA_VERSION = "schema_version"
ARTIFACT_SCHEMA_V1 = 1

# Task types that invoke agents (failure injection matrix)
AGENT_STAGE_TYPES: frozenset[TaskType] = frozenset(
    {
        TaskType.SELECT_TOPIC,
        TaskType.GENERATE_SCENARIO,
        TaskType.REVIEW_SCENARIO,
    }
)
