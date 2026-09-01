"""IT-INT-006 — Scenario E invalid AI output (INT-004)."""

from __future__ import annotations

from typing import Any

import pytest

from failure_injection import InjectionId
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    recording_only,
)

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-006")
def test_it_int_006_malformed_ai_output_structured_rejection_then_retry(
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-006: malformed AI output → structured rejection; retry progresses."""
    # Base config without permanent invalid injection; drive malformed via attempts.
    config = failure_injection_config_factory(enabled=False, active_injections=())
    worker = InjectableBoundaryWorker.create(config, hook_specs={})

    key = "wf-e:GENERATE_SCENARIO:1"
    good = {"schema_version": 1, "scenario": "ok", "provider": "fake"}
    outcomes = worker.execute_until_complete(
        workflow_id="wf-e",
        task_id="task-e-1",
        idempotency_key=key,
        artifact_payload=good,
        malformed_on_attempts=frozenset({1}),
        max_attempts=3,
    )

    assert outcomes[0].rejected is True
    assert outcomes[0].rejection_reason == "schema_invalid_model_output"
    assert outcomes[0].artifact is None
    assert outcomes[-1].completed is True
    assert worker.committed_artifacts[key] == good


@pytest.mark.it_int("IT-INT-006")
def test_it_int_006_finj_prv_invalid_rejects_without_corrupt_commit(
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-006 with FINJ-PRV-INVALID: structured rejection; no artifact commit."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_PRV_INVALID.value,),
    )
    hook = recording_only()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_PRV_INVALID: hook},
    )
    outcome = worker.execute_task(
        workflow_id="wf-e-invalid",
        task_id="task-e-invalid",
        idempotency_key="wf-e-invalid:GENERATE_SCENARIO:1",
    )
    assert outcome.rejected is True
    assert outcome.rejection_reason == "schema_invalid_model_output"
    assert worker.committed_artifacts == {}
    assert len(hook.calls) == 1
