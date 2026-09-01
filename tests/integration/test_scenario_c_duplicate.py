"""IT-INT-004 / IT-FINJ-002 — Scenario C duplicate delivery (INT-004)."""

from __future__ import annotations

from typing import Any

import pytest

from failure_injection import InjectionId
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    recording_only,
)

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-004")
@pytest.mark.it_int("IT-FINJ-002")
def test_it_int_004_duplicate_delivery_one_logical_completion(
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-004 / IT-FINJ-002: duplicate delivery → one logical completion."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_Q_DUP.value,),
    )
    dup_hook = recording_only()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_Q_DUP: dup_hook},
    )

    key = "wf-c:GENERATE_SCENARIO:1"
    payload = {"schema_version": 1, "content": "once", "provider": "fake"}

    first = worker.execute_task(
        workflow_id="wf-c",
        task_id="task-c-1",
        idempotency_key=key,
        artifact_payload=payload,
    )
    second = worker.execute_task(
        workflow_id="wf-c",
        task_id="task-c-1",
        idempotency_key=key,
        artifact_payload=payload,
    )

    assert first.completed is True
    assert first.idempotency_hit is False
    assert second.completed is True
    assert second.idempotency_hit is True
    assert worker.logical_completions["task-c-1"] == 1
    assert worker.delivery_counts["task-c-1"] == 2
    assert worker.committed_artifacts[key] == payload
    assert len(dup_hook.calls) >= 1
