"""IT-INT-001 / IT-INT-002 — Scenario A normal path (INT-003).

Uses injectable ScenarioWorkflowEngine + fake providers until LLD-RT-001 closes
(interface-gaps §4.1). No worker.handlers / agents internals.
"""

from __future__ import annotations

from typing import Any

import pytest

from api import PATH_WORKFLOW_BY_ID, PATH_WORKFLOW_OUTPUT, PATH_WORKFLOWS
from workflow.types import WorkflowState
from tests.integration.fakes import build_scenario_stack

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-001")
def test_it_int_001_api_initiate_reaches_awaiting_approval_with_artifacts(
    integration_app_config: Any,
) -> None:
    """IT-INT-001: POST /workflows → AWAITING_HUMAN_APPROVAL + artifacts (ACD-FR-059)."""
    stack = build_scenario_stack(integration_app_config)

    response = stack.client.post(PATH_WORKFLOWS, json={"actor": "integration-a"})
    assert response.status_code == 201
    body = response.json()
    workflow_id = body["workflow_id"]
    assert workflow_id
    assert body["state"] == WorkflowState.COLLECTING.value

    # Injectable fake-provider worker pipeline (LLD-RT-001 deferral).
    stack.engine.run_fake_provider_pipeline(workflow_id)
    assert stack.engine.provider_id_used == "fake"
    assert stack.engine.active_leases == ()

    status = stack.client.get(PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id))
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value

    output = stack.client.get(PATH_WORKFLOW_OUTPUT.format(workflow_id=workflow_id))
    assert output.status_code == 200
    package = output.json()["package"]
    assert package.get("topic_selection")
    assert package.get("scenario")
    assert package.get("critic")
    assert package["scenario"].get("provider") == "fake"


@pytest.mark.it_int("IT-INT-002")
def test_it_int_002_cli_initiate_status_via_api(
    integration_app_config: Any,
) -> None:
    """IT-INT-002: cli initiate → same workflow_id via GET status (ACD-CLI-001)."""
    stack = build_scenario_stack(integration_app_config)

    exit_code = stack.cli_app.run(
        ["initiate", "--actor", "cli-integration", "--workflow-id", "wf-cli-int-002"]
    )
    assert exit_code == 0

    stack.engine.run_fake_provider_pipeline("wf-cli-int-002")

    status = stack.client.get(PATH_WORKFLOW_BY_ID.format(workflow_id="wf-cli-int-002"))
    assert status.status_code == 200
    body = status.json()
    assert body["workflow_id"] == "wf-cli-int-002"
    assert body["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value
