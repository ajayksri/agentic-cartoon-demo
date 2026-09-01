"""Retry classification and backoff (LLD §4.5)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Retry with exponential backoff — transient provider
# and infrastructure failures are classified and retried; permanent errors fail fast.
# GUARDRAIL: Execution — permanent validation/config errors must not retry identically forever.

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agents.errors import (
    AgentConfigurationError,
    AgentInputValidationError,
    AgentOutputValidationError,
)
from collector.errors import CollectorError
from config.types import AppConfig, TaskType
from persistence.types import TaskRecord
from providers.errors import ProviderError
from task_queue.types import TaskMessage

from .errors import TaskExecutionError
from .types import TaskHandlerOutcome, TaskHandlerResult


@dataclass(frozen=True, slots=True)
class BackoffEntry:
    task_id: str
    ready_at: datetime
    attempt: int


class RetryClassifier:
    """Classifies failures and schedules exponential backoff."""

    def __init__(
        self,
        *,
        config: AppConfig,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or (lambda: datetime.now(UTC))
        self._backoff: dict[str, BackoffEntry] = {}
        self._lock = threading.Lock()

    def effective_attempt(
        self,
        *,
        task_record: TaskRecord,
        message: TaskMessage,
    ) -> int:
        return max(task_record.attempt, message.attempt)

    def should_defer(self, *, task_id: str) -> bool:
        with self._lock:
            entry = self._backoff.get(task_id)
        if entry is None:
            return False
        return self._clock() < entry.ready_at

    def classify_exception(self, err: BaseException) -> tuple[bool, str]:
        if isinstance(err, ProviderError):
            return err.retryable, err.error_class.value
        if isinstance(err, CollectorError):
            return err.retryable, err.code
        if isinstance(
            err,
            (
                AgentOutputValidationError,
                AgentInputValidationError,
                AgentConfigurationError,
            ),
        ):
            return False, err.code
        if isinstance(err, TaskExecutionError):
            return err.retryable, err.code
        return False, type(err).__name__

    def classify_handler_result(self, result: TaskHandlerResult) -> tuple[bool, str]:
        if result.outcome in {
            TaskHandlerOutcome.COMPLETED,
            TaskHandlerOutcome.DUPLICATE_REUSED,
        }:
            return False, ""
        if result.outcome == TaskHandlerOutcome.RETRYABLE_FAILURE:
            return True, result.error_class or "retryable_failure"
        if result.outcome == TaskHandlerOutcome.PERMANENT_FAILURE:
            return False, result.error_class or "permanent_failure"
        return False, result.error_class or "unknown"

    def schedule_backoff(
        self,
        *,
        task_id: str,
        attempt: int,
        task_type: TaskType,
    ) -> float:
        policy = self._config.get_retry_policy(task_type).backoff
        delay = min(
            policy.initial_seconds * (policy.multiplier ** (attempt - 1)),
            policy.max_seconds,
        )
        ready_at = self._clock() + timedelta(seconds=delay)
        with self._lock:
            self._backoff[task_id] = BackoffEntry(
                task_id=task_id,
                ready_at=ready_at,
                attempt=attempt,
            )
        return delay

    def is_exhausted(self, *, attempt: int, task_type: TaskType) -> bool:
        max_attempts = self._config.get_retry_policy(task_type).max_attempts
        return attempt >= max_attempts
