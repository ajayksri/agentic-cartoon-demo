"""IT-OBS-001–005 / IT-INT-012 — observability trace composition (INT-005).

Uses TracePipelineCapture + scenario/FINJ helpers. Fake provider only (ACD-NFR-011).
"""

from __future__ import annotations

from typing import Any

import pytest

from api import PATH_WORKFLOWS
from failure_injection import InjectionId
from tests.integration.fakes import build_scenario_stack
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    recording_only,
)
from tests.integration.fakes.trace_pipeline import (
    TracePipelineCapture,
    parse_traceparent,
)
from workflow.types import WorkflowState

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@pytest.mark.it_int("IT-OBS-001")
def test_it_obs_001_api_trace_consumed_by_coordinator(
    integration_app_config: Any,
) -> None:
    """IT-OBS-001: API request injects trace context consumed by coordinator."""
    pipeline = TracePipelineCapture()
    inbound = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    api_ctx = pipeline.start_api_span(inbound_traceparent=inbound, workflow_id="wf-obs-1")
    coord_ctx = pipeline.coordinator_span(api_ctx, workflow_id="wf-obs-1")

    assert api_ctx.trace_id == parse_traceparent(inbound).trace_id
    assert coord_ctx.trace_id == api_ctx.trace_id
    coord_spans = [s for s in pipeline.spans if s.service == "coordinator"]
    assert len(coord_spans) == 1
    assert coord_spans[0].parent_span_id == api_ctx.span_id
    assert coord_spans[0].trace_id == api_ctx.trace_id


@pytest.mark.it_int("IT-OBS-002")
def test_it_obs_002_queue_carrier_reaches_worker(
    integration_app_config: Any,
) -> None:
    """IT-OBS-002: Queue message carries trace context to worker."""
    del integration_app_config
    pipeline = TracePipelineCapture()
    api_ctx = pipeline.start_api_span(workflow_id="wf-obs-2")
    coord_ctx = pipeline.coordinator_span(api_ctx, workflow_id="wf-obs-2")
    carrier = pipeline.inject_queue_carrier(coord_ctx)

    assert "traceparent" in carrier
    worker_ctx = pipeline.worker_span_from_carrier(
        carrier,
        workflow_id="wf-obs-2",
        task_id="task-obs-2",
    )
    assert worker_ctx.trace_id == api_ctx.trace_id
    assert pipeline.queue_carriers[0]["traceparent"] == carrier["traceparent"]
    remote = parse_traceparent(carrier["traceparent"])
    assert remote.trace_id == coord_ctx.trace_id
    assert remote.span_id == coord_ctx.span_id


@pytest.mark.it_int("IT-OBS-003")
@pytest.mark.it_int("IT-INT-012")
def test_it_obs_003_and_it_int_012_end_to_end_span_chain(
    integration_app_config: Any,
) -> None:
    """IT-OBS-003 / IT-INT-012: spans link API → worker → fake provider."""
    stack = build_scenario_stack(integration_app_config)
    inbound = "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01"
    response = stack.client.post(
        PATH_WORKFLOWS,
        json={"actor": "obs-e2e", "workflow_id": "wf-obs-e2e"},
        headers={"traceparent": inbound},
    )
    assert response.status_code == 201
    workflow_id = response.json()["workflow_id"]

    pipeline = TracePipelineCapture()
    provider_ctx = pipeline.run_end_to_end(
        workflow_id=workflow_id,
        task_id=f"task-{workflow_id}",
        inbound_traceparent=inbound,
    )
    stack.engine.run_fake_provider_pipeline(workflow_id)
    status = stack.client.get(f"/workflows/{workflow_id}")
    assert status.json()["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value

    expected_trace = parse_traceparent(inbound).trace_id
    assert provider_ctx.trace_id == expected_trace
    services = pipeline.services_for_trace(expected_trace)
    assert {"api", "coordinator", "worker", "provider"} <= services
    assert all(s.trace_id == expected_trace for s in pipeline.spans_for_trace(expected_trace))
    provider_spans = [s for s in pipeline.spans if s.service == "provider"]
    assert provider_spans[0].attributes.get("provider") == "fake"


@pytest.mark.it_int("IT-OBS-004")
def test_it_obs_004_trace_continuity_after_redelivery(
    integration_app_config: Any,
) -> None:
    """IT-OBS-004: Same trace_id after task redelivery."""
    del integration_app_config
    pipeline = TracePipelineCapture()
    provider_ctx = pipeline.run_end_to_end(
        workflow_id="wf-obs-4",
        task_id="task-obs-4",
        attempt=1,
    )
    carrier = pipeline.queue_carriers[0]
    redelivered = pipeline.redeliver(
        carrier,
        workflow_id="wf-obs-4",
        task_id="task-obs-4",
        attempt=2,
    )
    assert redelivered.trace_id == provider_ctx.trace_id
    worker_attempts = [
        s.attributes.get("task_attempt")
        for s in pipeline.spans
        if s.service == "worker" and s.trace_id == provider_ctx.trace_id
    ]
    assert worker_attempts == [1, 2]


@pytest.mark.it_int("IT-OBS-005")
def test_it_obs_005_idempotency_hit_visible_in_metrics_and_logs(
    failure_injection_config_factory: Any,
) -> None:
    """IT-OBS-005: Idempotency hit visible in metrics and structured logs after duplicate."""
    config = failure_injection_config_factory(
        enabled=True,
        active_injections=(InjectionId.FINJ_Q_DUP.value,),
    )
    dup_hook = recording_only()
    worker = InjectableBoundaryWorker.create(
        config,
        hook_specs={InjectionId.FINJ_Q_DUP: dup_hook},
    )
    pipeline = TracePipelineCapture()
    root = pipeline.run_end_to_end(
        workflow_id="wf-obs-5",
        task_id="task-obs-5",
    )
    key = "wf-obs-5:COLLECT:1"
    payload = {"schema_version": 1, "content": "once", "provider": "fake"}
    first = worker.execute_task(
        workflow_id="wf-obs-5",
        task_id="task-obs-5",
        idempotency_key=key,
        artifact_payload=payload,
    )
    second = worker.execute_task(
        workflow_id="wf-obs-5",
        task_id="task-obs-5",
        idempotency_key=key,
        artifact_payload=payload,
    )
    assert first.completed is True
    assert second.idempotency_hit is True

    pipeline.record_idempotency_hit(
        workflow_id="wf-obs-5",
        task_id="task-obs-5",
        trace_id=root.trace_id,
    )
    assert any(m.name == "worker_idempotency_hits_total" for m in pipeline.metrics)
    assert any(log.event == "idempotency_hit" for log in pipeline.logs)
    assert any(
        s.attributes.get("idempotency_hit") is True
        for s in pipeline.spans
        if s.service == "worker"
    )
