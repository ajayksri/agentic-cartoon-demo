"""IT-INT-005 / IT-FINJ-003 — Scenario D rate limit (INT-004)."""

from __future__ import annotations

from typing import Any

import pytest

from failure_injection import InjectionId
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    rate_limit_on_first_call,
)

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-005")
@pytest.mark.it_int("IT-FINJ-003")
def test_it_int_005_provider_rate_limit_retries_without_state_loss(
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-005 / IT-FINJ-003: rate-limit fake → retry without state loss."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_PRV_RATE.value,),
    )
    rate_hook = rate_limit_on_first_call()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_PRV_RATE: rate_hook},
    )

    key = "wf-d:SELECT_TOPIC:1"
    payload = {"schema_version": 1, "topic": "kept", "provider": "fake"}
    outcomes = worker.execute_until_complete(
        workflow_id="wf-d",
        task_id="task-d-1",
        idempotency_key=key,
        artifact_payload=payload,
        max_attempts=4,
    )

    assert outcomes[0].rate_limited is True
    assert outcomes[0].completed is False
    assert outcomes[0].artifact is None
    assert outcomes[-1].completed is True
    assert worker.committed_artifacts[key] == payload
    assert worker.logical_completions["task-d-1"] == 1
    assert len(rate_hook.calls) >= 1
