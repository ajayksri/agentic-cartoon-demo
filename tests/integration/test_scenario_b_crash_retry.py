"""IT-INT-003 / IT-FINJ-001 — Scenario B crash/retry (INT-004)."""

from __future__ import annotations

from typing import Any

import pytest

from failure_injection import InjectionId
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    crash_on_first_call,
)

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-003")
@pytest.mark.it_int("IT-FINJ-001")
def test_it_int_003_post_commit_crash_safe_redelivery(
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-003 / IT-FINJ-001: post-commit crash → redelivery; no corrupt commit."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_WKR_POST_COMMIT.value,),
    )
    post_commit = crash_on_first_call()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_WKR_POST_COMMIT: post_commit},
    )

    payload = {"schema_version": 1, "content": "stable-artifact", "provider": "fake"}
    key = "wf-b:SELECT_TOPIC:1"
    outcomes = worker.execute_until_complete(
        workflow_id="wf-b",
        task_id="task-b-1",
        idempotency_key=key,
        artifact_payload=payload,
        max_attempts=3,
    )

    assert len(outcomes) >= 2
    assert outcomes[0].crashed is True
    assert outcomes[0].artifact == payload
    assert outcomes[-1].completed is True
    assert outcomes[-1].idempotency_hit is True
    assert worker.committed_artifacts[key] == payload
    assert worker.logical_completions["task-b-1"] == 1
    assert worker.delivery_counts["task-b-1"] >= 2
    assert len(post_commit.calls) >= 1


@pytest.mark.it_int("IT-FINJ-001")
def test_it_finj_001_post_agent_hook_fires_and_redelivers(
    failure_injection_config_factory: Any,
) -> None:
    """IT-FINJ-001: FINJ-WKR-POST-AGENT fires; task redelivered after crash."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_WKR_POST_AGENT.value,),
    )
    hook = crash_on_first_call()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_WKR_POST_AGENT: hook},
    )
    outcomes = worker.execute_until_complete(
        workflow_id="wf-b-agent",
        task_id="task-b-agent",
        idempotency_key="wf-b-agent:COLLECT:1",
        max_attempts=3,
    )
    assert outcomes[0].crashed is True
    assert outcomes[-1].completed is True
    assert len(hook.calls) >= 1
    assert InjectionId.FINJ_WKR_POST_AGENT.value in worker.observed_active_injections
