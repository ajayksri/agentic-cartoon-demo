"""Runtime module constants — streams, defaults, metric names, probe tuning."""

from __future__ import annotations

from config.types import TaskType

DEFAULT_API_HOST: str = "0.0.0.0"
DEFAULT_API_PORT: int = 8000
DEFAULT_HTTP_SHUTDOWN_GRACE_SECONDS: float = 30.0

READINESS_PROBE_TIMEOUT_SECONDS: float = 2.0
PROBE_NAME_POSTGRES: str = "postgres"
PROBE_NAME_REDIS: str = "redis"

DEFAULT_WORKER_BLOCK_MS: int = 5000
DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS: float = 30.0

WORKER_STREAM_BY_TASK_TYPE: dict[TaskType, str] = {
    TaskType.COLLECT: "cartoon:tasks:collect",
    TaskType.SELECT_TOPIC: "cartoon:tasks:select_topic",
    TaskType.GENERATE_SCENARIO: "cartoon:tasks:generate_scenario",
    TaskType.REVIEW_SCENARIO: "cartoon:tasks:review_scenario",
}

WORKER_GROUP_BY_TASK_TYPE: dict[TaskType, str] = {
    TaskType.COLLECT: "cartoon:workers:collect",
    TaskType.SELECT_TOPIC: "cartoon:workers:select_topic",
    TaskType.GENERATE_SCENARIO: "cartoon:workers:generate_scenario",
    TaskType.REVIEW_SCENARIO: "cartoon:workers:review_scenario",
}

DEFAULT_WORKER_ROLE: TaskType = TaskType.COLLECT

OUTBOX_RETRY_INITIAL_SECONDS: float = 1.0
OUTBOX_RETRY_MAX_SECONDS: float = 30.0
OUTBOX_RETRY_MAX_ATTEMPTS: int = 5

METRIC_BOOTSTRAP_FAILURES: str = "runtime_bootstrap_failures_total"
METRIC_OUTBOX_PUBLISHED: str = "runtime_outbox_published_total"
METRIC_OUTBOX_PUBLISH_FAILURES: str = "runtime_outbox_publish_failures_total"
METRIC_RECONCILIATION_REPAIRS: str = "runtime_reconciliation_repairs_total"

SCRIPT_API: str = "cartoon-demo-api"
SCRIPT_COORDINATOR: str = "cartoon-demo-coordinator"
SCRIPT_WORKER: str = "cartoon-demo-worker"
