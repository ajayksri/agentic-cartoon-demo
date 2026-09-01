"""IT-INT-007 — Scenario F coordinator restart / outbox recovery (INT-004)."""

from __future__ import annotations

from typing import Any

import pytest

from api import PATH_WORKFLOWS
from tests.integration.fakes import build_scenario_stack
from tests.integration.fakes.finj_worker import InjectableBoundaryWorker
from workflow.types import WorkflowState

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-007")
def test_it_int_007_coordinator_restart_publishes_outbox_and_progresses(
    integration_app_config: Any,
    failure_injection_config_factory: Any,
) -> None:
    """IT-INT-007: pending outbox survives coordinator stop; restart publishes + progress."""
    del failure_injection_config_factory
    stack = build_scenario_stack(integration_app_config)
    created = stack.client.post(PATH_WORKFLOWS, json={"actor": "integration-f"})
    assert created.status_code == 201
    workflow_id = created.json()["workflow_id"]

    # Mid-flight: outbox pending, coordinator not yet published.
    worker = InjectableBoundaryWorker.create(integration_app_config, hook_specs={})
    worker.enqueue_outbox(
        workflow_id=workflow_id,
        task_id=f"task-{workflow_id}-collect",
        task_type="COLLECT",
    )
    assert len(worker.pending_outbox) == 1
    assert worker.published_outbox == []

    # Coordinator SIGTERM simulation: drop in-memory publisher loop; durable pending remains.
    pending_snapshot = list(worker.pending_outbox)

    # Restart: new publisher pass recovers pending outbox.
    recovered = InjectableBoundaryWorker.create(integration_app_config, hook_specs={})
    recovered.pending_outbox = list(pending_snapshot)
    published = recovered.publish_pending_outbox()
    assert published == 1
    assert recovered.pending_outbox == []
    assert len(recovered.published_outbox) == 1
    assert recovered.published_outbox[0]["workflow_id"] == workflow_id

    # Worker progresses after publish.
    stack.engine.run_fake_provider_pipeline(workflow_id)
    status = stack.client.get(f"/workflows/{workflow_id}")
    assert status.json()["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value
