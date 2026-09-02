"""Pre-code test mold for WKR-004 — RetryClassifier (LLD §4.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agents import AgentOutputValidationError
from collector.errors import CollectorFetchError
from config.app_config import AppConfigFactory
from config.credentials import CredentialResolver
from config.draft import (
    AgentDraft,
    BackoffDraft,
    CollectionDraft,
    ConfigDraft,
    FailureInjectionDraft,
    InfrastructureDraft,
    PostgresDraft,
    ProviderDraft,
    RedisDraft,
    RetryPolicyDraft,
    TimeoutDraft,
    WorkerDraft,
    WorkflowDraft,
)
from config.types import AgentId, ProviderId, TaskType
from persistence import PayloadReference, TaskRecord, TaskStatus
from persistence.types import TaskType as PersTaskType
from providers import ProviderTimeoutError
from task_queue import TaskMessage
from worker import TaskHandlerOutcome, TaskHandlerResult
from workflow.types import TransitionSignal

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _config(*, max_attempts: int = 3) -> object:
    backoff = BackoffDraft(initial_seconds=2.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=max_attempts, backoff=backoff)
    draft = ConfigDraft(
        config_version="1",
        infrastructure=InfrastructureDraft(
            postgres=PostgresDraft(
                host="localhost",
                port=5432,
                database="cartoon",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisDraft(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="prompts/topic_selector/v1.txt",
            ),
        },
        providers={
            ProviderId.FAKE: ProviderDraft(
                api_key_env="FAKE_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=10, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={task: retry_policy for task in TaskType},
        timeouts={
            ProviderId.FAKE: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(enabled=False, active_injections=[]),
    )
    return AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)


def _classifier(*, config: object | None = None, now: datetime | None = None) -> object:
    from worker.retry import RetryClassifier

    return RetryClassifier(config=config or _config(), clock=lambda: now or _FIXED_NOW)


def _task_record(*, attempt: int = 1) -> TaskRecord:
    return TaskRecord(
        task_id="task-retry-1",
        workflow_id="wf-retry-1",
        task_type=PersTaskType.COLLECT,
        attempt=attempt,
        status=TaskStatus.DISPATCHED,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def _message(*, attempt: int = 1) -> TaskMessage:
    return TaskMessage(
        task_id="task-retry-1",
        workflow_id="wf-retry-1",
        task_type=TaskType.COLLECT,
        attempt=attempt,
        created_at=_FIXED_NOW,
        payload_reference="ref://pl-1",
    )


def test_backoff_formula_matches_retry_policy() -> None:
    """LLD §4.5: delay = min(initial * multiplier^(attempt-1), max_seconds)."""
    classifier = _classifier()
    delay = classifier.schedule_backoff(  # type: ignore[attr-defined]
        task_id="task-retry-1",
        attempt=2,
        task_type=TaskType.COLLECT,
    )
    assert delay == 4.0


@pytest.mark.wkr_tc("021")
def test_is_exhausted_at_max_attempts_boundary() -> None:
    """WKR-TC-021: attempt == max_attempts is exhausted."""
    classifier = _classifier(config=_config(max_attempts=3))
    assert classifier.is_exhausted(attempt=3, task_type=TaskType.COLLECT) is True  # type: ignore[attr-defined]
    assert classifier.is_exhausted(attempt=2, task_type=TaskType.COLLECT) is False  # type: ignore[attr-defined]


def test_effective_attempt_uses_max_of_record_and_message() -> None:
    classifier = _classifier()
    attempt = classifier.effective_attempt(  # type: ignore[attr-defined]
        task_record=_task_record(attempt=2),
        message=_message(attempt=3),
    )
    assert attempt == 3


def test_should_defer_when_backoff_not_ready() -> None:
    from worker.retry import RetryClassifier

    clock_time = _FIXED_NOW

    def clock() -> datetime:
        return clock_time

    classifier = RetryClassifier(config=_config(), clock=clock)
    classifier.schedule_backoff(  # type: ignore[attr-defined]
        task_id="task-retry-1",
        attempt=1,
        task_type=TaskType.COLLECT,
    )
    assert classifier.should_defer(task_id="task-retry-1") is True  # type: ignore[attr-defined]
    clock_time = _FIXED_NOW + timedelta(seconds=10)
    assert classifier.should_defer(task_id="task-retry-1") is False  # type: ignore[attr-defined]


def test_classify_provider_timeout_as_retryable() -> None:
    """WKR-TC-022 seam: provider timeout classified retryable."""
    classifier = _classifier()
    retryable, error_class = classifier.classify_exception(ProviderTimeoutError("deadline"))  # type: ignore[attr-defined]
    assert retryable is True
    assert "TIMEOUT" in error_class.upper() or error_class == "PRV_TIMEOUT"


def test_classify_agent_validation_as_non_retryable() -> None:
    """WKR-TC-024 seam: agent validation errors not retryable."""
    classifier = _classifier()
    err = AgentOutputValidationError("invalid output", agent_id=AgentId.TOPIC_SELECTOR)
    retryable, _ = classifier.classify_exception(err)  # type: ignore[attr-defined]
    assert retryable is False


def test_classify_collector_error_uses_code() -> None:
    classifier = _classifier()
    retryable, error_class = classifier.classify_exception(CollectorFetchError("fetch failed"))  # type: ignore[attr-defined]
    assert retryable is True
    assert error_class == "COL_FETCH"


def test_classify_handler_result_completed_not_failure() -> None:
    classifier = _classifier()
    result = TaskHandlerResult(
        outcome=TaskHandlerOutcome.COMPLETED,
        transition_signal=TransitionSignal.STAGE_COMPLETED,
    )
    retryable, _ = classifier.classify_handler_result(result)  # type: ignore[attr-defined]
    assert retryable is False
