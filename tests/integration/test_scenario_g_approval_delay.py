"""IT-INT-008 — Scenario G approval delay (INT-003)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from api import PATH_WORKFLOW_APPROVAL, PATH_WORKFLOW_BY_ID, PATH_WORKFLOWS
from workflow.types import ApprovalAction, WorkflowState
from tests.integration.fakes import build_scenario_stack

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-INT-008")
def test_it_int_008_approval_wait_has_no_leases_then_approval_resumes(
    integration_app_config: Any,
) -> None:
    """IT-INT-008: approval wait holds no leases; POST approval resumes (ACD-FR-065)."""
    stack = build_scenario_stack(integration_app_config)

    created = stack.client.post(PATH_WORKFLOWS, json={"actor": "integration-g"})
    assert created.status_code == 201
    workflow_id = created.json()["workflow_id"]

    stack.engine.run_fake_provider_pipeline(workflow_id)
    assert stack.engine.active_leases == ()

    status = stack.client.get(PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id))
    assert status.json()["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value

    # Wall-clock delay with no worker tasks / leases (ACD-FR-013).
    time.sleep(0.05)
    assert stack.engine.active_leases == ()
    delayed = stack.client.get(PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id))
    assert delayed.json()["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value

    approval = stack.client.post(
        PATH_WORKFLOW_APPROVAL.format(workflow_id=workflow_id),
        json={"action": ApprovalAction.APPROVE.value, "actor": "approver"},
    )
    assert approval.status_code == 200
    approval_body = approval.json()
    assert approval_body["to_state"] == WorkflowState.APPROVED.value
    assert approval_body["from_state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value

    final = stack.client.get(PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id))
    assert final.json()["state"] == WorkflowState.APPROVED.value
    assert stack.engine.active_leases == ()
