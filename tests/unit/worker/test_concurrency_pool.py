"""Pre-code test mold for WKR-005 — ConcurrencyPool (LLD §4.6)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pytest

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
from task_queue import PendingDelivery, TaskMessage

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _config(*, topic_concurrency: int = 2) -> object:
    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
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
                prompt_file="tests/fixtures/agents/prompts/topic_selector.txt",
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/scenario_generator.txt",
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/critic.txt",
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
            topic_selector_concurrency=topic_concurrency,
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


def _pool(*, config: object | None = None) -> object:
    from worker.concurrency import ConcurrencyPool

    return ConcurrencyPool(config=config or _config(), clock=lambda: _FIXED_NOW)


def _delivery(task_type: TaskType = TaskType.SELECT_TOPIC) -> PendingDelivery:
    return PendingDelivery(
        message=TaskMessage(
            task_id="task-conc-1",
            workflow_id="wf-conc-1",
            task_type=task_type,
            attempt=1,
            created_at=_FIXED_NOW,
            payload_reference="ref://pl-1",
        ),
        stream="cartoon:tasks",
        consumer_group="workers",
        delivery_id="del-1",
        dequeued_at=_FIXED_NOW,
    )


def test_collect_limit_fixed_at_one() -> None:
    """LLD-WKR-003 deferred: COLLECT uses COLLECT_CONCURRENCY_LIMIT regardless of config."""
    from worker.constants import COLLECT_CONCURRENCY_LIMIT

    pool = _pool(config=_config(topic_concurrency=5))
    in_flight = threading.Semaphore(0)
    started = threading.Event()
    gate = threading.Event()

    def _worker(_delivery: PendingDelivery) -> None:
        started.set()
        gate.wait(timeout=2.0)
        in_flight.release()

    pool.submit(_worker, _delivery(task_type=TaskType.COLLECT))  # type: ignore[attr-defined]
    pool.submit(_worker, _delivery(task_type=TaskType.COLLECT))  # type: ignore[attr-defined]
    started.wait(timeout=2.0)
    assert not in_flight.acquire(blocking=False)
    gate.set()
    assert COLLECT_CONCURRENCY_LIMIT == 1


@pytest.mark.wkr_tc("031")
def test_semaphore_enforces_at_most_n_in_flight() -> None:
    """WKR-TC-031 unit seam: third acquire blocks until a slot is released."""
    pool = _pool(config=_config(topic_concurrency=2))
    slots: list[object] = []
    third_blocked = threading.Event()

    slots.append(pool.acquire_blocking(TaskType.SELECT_TOPIC))  # type: ignore[attr-defined]
    slots.append(pool.acquire_blocking(TaskType.SELECT_TOPIC))  # type: ignore[attr-defined]

    def _try_third() -> None:
        pool.acquire_blocking(TaskType.SELECT_TOPIC)  # type: ignore[attr-defined]
        third_blocked.set()

    threading.Thread(target=_try_third, daemon=True).start()
    time.sleep(0.05)
    assert not third_blocked.is_set()
    pool.release(slots.pop())  # type: ignore[attr-defined]
    time.sleep(0.05)
    assert third_blocked.wait(timeout=2.0)
    pool.release(slots.pop())  # type: ignore[attr-defined]


def test_submit_does_not_acquire_semaphore() -> None:
    """LLD §4.6: submit schedules only; acquire owned by _process_delivery."""
    pool = _pool()
    slot = pool.acquire_blocking(TaskType.SELECT_TOPIC)  # type: ignore[attr-defined]
    pool.submit(lambda _d: None, _delivery())  # type: ignore[attr-defined]
    second_slot = pool.acquire_blocking(TaskType.SELECT_TOPIC)  # type: ignore[attr-defined]
    pool.release(second_slot)  # type: ignore[attr-defined]
    pool.release(slot)  # type: ignore[attr-defined]


def test_independent_task_types_use_independent_semaphores() -> None:
    pool = _pool(config=_config(topic_concurrency=1))
    collect_slot = pool.acquire_blocking(TaskType.COLLECT)  # type: ignore[attr-defined]
    select_slot = pool.acquire_blocking(TaskType.SELECT_TOPIC)  # type: ignore[attr-defined]
    assert collect_slot.task_type == TaskType.COLLECT  # type: ignore[attr-defined]
    assert select_slot.task_type == TaskType.SELECT_TOPIC  # type: ignore[attr-defined]
    pool.release(collect_slot)  # type: ignore[attr-defined]
    pool.release(select_slot)  # type: ignore[attr-defined]


def test_shutdown_respects_timeout_parameter() -> None:
    pool = _pool()
    pool.shutdown(wait=True, timeout=0.1)  # type: ignore[attr-defined]
