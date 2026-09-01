"""Contract tests API-TC-001 through API-TC-023 (API-017).

Imports ONLY from the api package public surface (`api.__init__`).
Boundary imports for fixture injection live in helpers.py / conftest.py per LLD §14.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

from api import (
    ApiConflictError,
    ApiDependencies,
    ApiError,
    ApiErrorEnvelope,
    ApiInternalError,
    ApiNotFoundError,
    ApiValidationError,
    DependencyCheck,
    DependencyCheckStatus,
    HealthResponse,
    HealthStatus,
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    PATH_HEALTH,
    PATH_READY,
    PATH_WORKFLOW_APPROVAL,
    PATH_WORKFLOW_BY_ID,
    PATH_WORKFLOW_HISTORY,
    PATH_WORKFLOW_OUTPUT,
    PATH_WORKFLOW_TIMELINE,
    PATH_WORKFLOWS,
    ReadinessResponse,
    ReadinessStatus,
    ROUTE_APPROVAL,
    ROUTE_HEALTH,
    ROUTE_HISTORY,
    ROUTE_INITIATE,
    ROUTE_OUTPUT,
    ROUTE_READY,
    ROUTE_STATUS,
    ROUTE_TIMELINE,
    SubmitApprovalApiRequest,
    SubmitApprovalApiResponse,
    TimelineEventResponse,
    TransitionRecordResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
    create_api_router,
    handle_get_workflow_history,
    handle_get_workflow_output,
    handle_get_workflow_status,
    handle_get_workflow_timeline,
    handle_health,
    handle_initiate_workflow,
    handle_readiness,
    handle_submit_approval,
)

from .helpers import (
    _EXPECTED_ROUTE_BINDINGS,
    assert_envelope_shape,
    assert_readiness_dependency_checks,
    call_with_engine_count_guard,
    configure_engine,
    dto_field_names_match_interfaces,
    empty_workflow_history,
    invalid_approval_envelope,
    invalid_approval_error,
    make_test_client,
    mixed_readiness_probes,
    run_async,
    sample_approval_result,
    sample_initiate_result,
    sample_workflow_history,
    sample_workflow_output,
    sample_workflow_status,
    sample_workflow_timeline,
    terminal_workflow_envelope,
    terminal_workflow_error,
    valid_approval_request,
    workflow_not_found_envelope,
    workflow_not_found_error,
)

pytestmark = []

_FORBIDDEN_IMPORT_PREFIXES = (
    "worker",
    "agents",
    "providers",
    "task_queue",
    "persistence",
    "collector",
)

_PUBLIC_EXPORTS: tuple[str, ...] = (
    "create_api_router",
    "ApiRouterFactory",
    "ApiDependencies",
    "ReadinessProbe",
    "MutatingRouteContext",
    "HealthStatus",
    "ReadinessStatus",
    "DependencyCheckStatus",
    "InitiateWorkflowApiRequest",
    "InitiateWorkflowApiResponse",
    "WorkflowStatusResponse",
    "TransitionRecordResponse",
    "WorkflowHistoryResponse",
    "WorkflowOutputResponse",
    "SubmitApprovalApiRequest",
    "SubmitApprovalApiResponse",
    "TimelineEventResponse",
    "WorkflowTimelineResponse",
    "HealthResponse",
    "DependencyCheck",
    "ReadinessResponse",
    "ApiErrorEnvelope",
    "ApiError",
    "ApiValidationError",
    "ApiNotFoundError",
    "ApiConflictError",
    "ApiInternalError",
    "map_workflow_status",
    "map_workflow_history",
    "map_workflow_output",
    "map_workflow_timeline",
    "map_initiate_result",
    "map_approval_result",
    "map_transition_record",
    "map_timeline_event",
    "map_workflow_error",
    "ROUTE_INITIATE",
    "ROUTE_STATUS",
    "ROUTE_HISTORY",
    "ROUTE_OUTPUT",
    "ROUTE_APPROVAL",
    "ROUTE_TIMELINE",
    "ROUTE_HEALTH",
    "ROUTE_READY",
    "PATH_WORKFLOWS",
    "PATH_WORKFLOW_BY_ID",
    "PATH_WORKFLOW_HISTORY",
    "PATH_WORKFLOW_OUTPUT",
    "PATH_WORKFLOW_APPROVAL",
    "PATH_WORKFLOW_TIMELINE",
    "PATH_HEALTH",
    "PATH_READY",
)


@pytest.mark.api_tc("001")
def test_api_tc_001_router_factory_exposes_all_route_modules(
    api_router_under_test,
) -> None:
    """API-TC-001: create_api_router registers all eight route IDs (MOD-API-INV-004)."""
    router = api_router_under_test()
    registered = {
        (method, path)
        for method, path in (
            (method, path)
            for method, path in _route_pairs_from_router(router)
        )
    }
    for route_id, method, path in _EXPECTED_ROUTE_BINDINGS:
        assert (method, path) in registered, f"missing route {route_id} ({method} {path})"


@pytest.mark.api_tc("002")
def test_api_tc_002_public_types_importable_from_package_root() -> None:
    """API-TC-002: Public executable surface exports match interfaces.md §9."""
    import api

    for symbol in _PUBLIC_EXPORTS:
        assert hasattr(api, symbol), f"missing export {symbol}"
        assert symbol in api.__all__

    assert inspect.isclass(ApiDependencies)
    assert inspect.isfunction(create_api_router)
    assert ROUTE_INITIATE == "initiate"
    assert PATH_WORKFLOWS == "/workflows"


@pytest.mark.api_tc("003")
def test_api_tc_003_initiate_returns_workflow_id(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-003: Initiate returns non-empty workflow_id (ACD-API-001, MOD-API-INV-005)."""
    configure_engine(
        fake_workflow_engine,
        initiate_result=sample_initiate_result(workflow_id="wf-init-001"),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_initiate_workflow(
            deps=deps,
            request=InitiateWorkflowApiRequest(actor="contract-test"),
        ),
    )

    assert response.workflow_id
    assert response.state is not None


@pytest.mark.api_tc("004")
def test_api_tc_004_initiate_creates_trace_context(
    api_router_under_test,
    fake_workflow_engine,
    recording_telemetry,
) -> None:
    """API-TC-004: Initiate creates root span and trace_id (ACD-FR-034, MOD-API-INV-015)."""
    configure_engine(
        fake_workflow_engine,
        initiate_result=sample_initiate_result(workflow_id="wf-trace"),
    )
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)

    response = client.post(PATH_WORKFLOWS, json={"actor": "contract-test"})

    assert response.status_code == 201
    from .helpers import assert_initiate_trace_observability

    assert_initiate_trace_observability(
        response_body=response.json(),
        recording_telemetry=recording_telemetry,
        workflow_id="wf-trace",
    )


@pytest.mark.api_tc("005")
def test_api_tc_005_invalid_initiate_body_rejected(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-005: Invalid body returns validation envelope; engine not called (ACD-SEC-004)."""
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)
    oversize_actor = "x" * 4096

    delta = call_with_engine_count_guard(
        fake_workflow_engine,
        lambda: client.post(PATH_WORKFLOWS, json={"actor": oversize_actor}),
    )

    assert delta == 0
    response = client.post(PATH_WORKFLOWS, json={"actor": oversize_actor})
    assert response.status_code == 400
    envelope = ApiErrorEnvelope(**response.json())
    assert envelope.error_class == "API_VALIDATION"


@pytest.mark.api_tc("006")
def test_api_tc_006_status_returns_workflow_snapshot(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-006: Status handler returns workflow snapshot (ACD-API-002)."""
    configure_engine(
        fake_workflow_engine,
        status=sample_workflow_status(workflow_id="wf-collecting"),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_status(deps=deps, workflow_id="wf-collecting"),
    )

    assert isinstance(response, WorkflowStatusResponse)
    assert response.workflow_id == "wf-collecting"
    assert response.state is not None
    assert response.state_version >= 1


@pytest.mark.api_tc("007")
def test_api_tc_007_unknown_workflow_returns_404_envelope(
    api_router_under_test,
) -> None:
    """API-TC-007: WorkflowNotFoundError maps to WF_NOT_FOUND 404 (ACD-API-002)."""
    from .helpers import load_fakes

    engine_cls, _ = load_fakes()
    engine = engine_cls()
    configure_engine(
        engine,
        status_error=workflow_not_found_error(workflow_id="wf-missing"),
    )
    router = api_router_under_test(engine=engine)
    client = make_test_client(router)

    response = client.get("/workflows/wf-missing")

    assert response.status_code == 404
    envelope = ApiErrorEnvelope(**response.json())
    assert envelope.error_class == "WF_NOT_FOUND"
    assert envelope.workflow_id == "wf-missing"


@pytest.mark.api_tc("008")
def test_api_tc_008_history_returns_ordered_transitions(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-008: History returns two chronologically ordered transitions (ACD-API-003)."""
    history = sample_workflow_history(workflow_id="wf-history-order")
    configure_engine(fake_workflow_engine, history=history)
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_history(deps=deps, workflow_id="wf-history-order"),
    )

    assert len(response.transitions) == 2
    occurred = [transition.occurred_at for transition in response.transitions]
    assert occurred == sorted(occurred)


@pytest.mark.api_tc("009")
def test_api_tc_009_empty_history_for_new_workflow(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-009: Empty history tuple returned without error (ACD-API-003)."""
    configure_engine(
        fake_workflow_engine,
        history=empty_workflow_history(workflow_id="wf-new-empty"),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_history(deps=deps, workflow_id="wf-new-empty"),
    )

    assert response.transitions == ()


@pytest.mark.api_tc("010")
def test_api_tc_010_output_returns_package_when_available(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-010: Complete output package returns is_complete=True (ACD-API-004, ACD-FR-039)."""
    configure_engine(
        fake_workflow_engine,
        output=sample_workflow_output(workflow_id="wf-complete", is_complete=True),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_output(deps=deps, workflow_id="wf-complete"),
    )

    assert response.is_complete is True
    assert response.package


@pytest.mark.api_tc("011")
def test_api_tc_011_partial_output_for_incomplete_workflow(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-011: Partial output returns is_complete=False (ACD-API-004)."""
    configure_engine(
        fake_workflow_engine,
        output=sample_workflow_output(workflow_id="wf-partial", is_complete=False),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_output(deps=deps, workflow_id="wf-partial"),
    )

    assert response.is_complete is False
    assert response.failure_reason is not None


@pytest.mark.api_tc("012")
def test_api_tc_012_approve_succeeds_from_awaiting_human_approval(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-012: APPROVE succeeds from AWAITING_HUMAN_APPROVAL (ACD-API-005, ACD-FR-014)."""
    configure_engine(
        fake_workflow_engine,
        approval_result=sample_approval_result(workflow_id="wf-approve-ok"),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )
    response = run_async(
        handle_submit_approval(
            deps=deps,
            workflow_id="wf-approve-ok",
            request=valid_approval_request(),
        ),
    )

    assert response.to_state.value == "APPROVED"


@pytest.mark.api_tc("013")
def test_api_tc_013_approval_rejected_from_wrong_state(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-013: InvalidApprovalActionError maps to WF_INVALID_APPROVAL 409 (ACD-SEC-006)."""
    configure_engine(
        fake_workflow_engine,
        approval_error=invalid_approval_error(workflow_id="wf-invalid-approval"),
    )
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)

    response = client.post(
        "/workflows/wf-invalid-approval/approval",
        json={"action": "APPROVE"},
    )

    assert response.status_code == 409
    envelope = ApiErrorEnvelope(**response.json())
    assert envelope.error_class == "WF_INVALID_APPROVAL"


@pytest.mark.api_tc("014")
def test_api_tc_014_invalid_action_enum_rejected_before_engine(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-014: Unknown action rejected before workflow call (MOD-API-INV-008)."""
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)

    delta = call_with_engine_count_guard(
        fake_workflow_engine,
        lambda: client.post(
            "/workflows/wf-approval/approval",
            json={"action": "MAYBE"},
        ),
    )

    assert delta == 0
    response = client.post(
        "/workflows/wf-approval/approval",
        json={"action": "MAYBE"},
    )
    assert response.status_code == 400
    envelope = ApiErrorEnvelope(**response.json())
    assert envelope.error_class == "API_VALIDATION"


@pytest.mark.api_tc("015")
def test_api_tc_015_duplicate_approval_on_terminal_workflow_rejected(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-015: WorkflowTerminalError returns terminal conflict envelope (ACD-INT-010)."""
    configure_engine(
        fake_workflow_engine,
        approval_error=terminal_workflow_error(workflow_id="wf-terminal"),
    )
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)

    response = client.post(
        "/workflows/wf-terminal/approval",
        json={"action": "APPROVE"},
    )

    assert response.status_code == 409
    envelope = ApiErrorEnvelope(**response.json())
    assert envelope.error_class == "WF_TERMINAL"


@pytest.mark.api_tc("016")
def test_api_tc_016_timeline_returns_ordered_events(
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-016: Timeline ordered by occurred_at ascending (ACD-API-007, ACD-FR-066)."""
    configure_engine(
        fake_workflow_engine,
        timeline=sample_workflow_timeline(workflow_id="wf-timeline-order"),
    )
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )

    response = run_async(
        handle_get_workflow_timeline(deps=deps, workflow_id="wf-timeline-order"),
    )

    occurred = [event.occurred_at for event in response.events]
    assert occurred == sorted(occurred)


@pytest.mark.api_tc("017")
def test_api_tc_017_health_returns_ok_when_process_alive() -> None:
    """API-TC-017: Health handler returns ok status (ACD-API-006, MOD-API-INV-013)."""
    from .helpers import build_health_dependencies

    response = run_async(handle_health(deps=build_health_dependencies()))

    assert isinstance(response, HealthResponse)
    assert response.status == HealthStatus.OK


@pytest.mark.api_tc("018")
def test_api_tc_018_readiness_reflects_injected_probes(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-018: Mixed probes yield HTTP 503 and not_ready body (ACD-API-006, CG-API-003)."""
    router = api_router_under_test(
        engine=fake_workflow_engine,
        readiness_probes=mixed_readiness_probes(),
    )
    client = make_test_client(router)

    response = client.get(PATH_READY)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == ReadinessStatus.NOT_READY.value
    assert_readiness_dependency_checks(
        tuple(
            DependencyCheck(
                name=check["name"],
                status=DependencyCheckStatus(check["status"]),
                detail=check.get("detail"),
            )
            for check in body["checks"]
        ),
    )


@pytest.mark.api_tc("019")
def test_api_tc_019_all_error_responses_use_api_error_envelope_shape(
    api_router_under_test,
    fake_workflow_engine,
) -> None:
    """API-TC-019: Error paths emit ApiErrorEnvelope shape (ACD-API-008, MOD-API-INV-010)."""
    validation = ApiValidationError("invalid field").to_envelope()
    not_found = ApiNotFoundError("missing", workflow_id="wf-1").to_envelope()
    conflict = ApiConflictError("conflict", workflow_id="wf-2").to_envelope()
    internal = ApiInternalError("internal").to_envelope()
    mapped_not_found = workflow_not_found_envelope()
    mapped_invalid_approval = invalid_approval_envelope()
    mapped_terminal = terminal_workflow_envelope()

    for envelope in (
        validation,
        not_found,
        conflict,
        internal,
        mapped_not_found,
        mapped_invalid_approval,
        mapped_terminal,
    ):
        assert_envelope_shape(envelope)

    configure_engine(
        fake_workflow_engine,
        status_error=workflow_not_found_error(workflow_id="wf-http-missing"),
    )
    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)
    from .helpers import http_error_envelope_from_client

    http_cases: tuple[tuple[Callable[[], Any], str], ...] = (
        (
            lambda: client.post(PATH_WORKFLOWS, json={"actor": "x" * 4096}),
            "API_VALIDATION",
        ),
        (
            lambda: client.get("/workflows/wf-http-missing"),
            "WF_NOT_FOUND",
        ),
        (
            lambda: client.post(
                "/workflows/wf-http-missing/approval",
                json={"action": "MAYBE"},
            ),
            "API_VALIDATION",
        ),
    )
    for request_call, expected_class in http_cases:
        envelope = http_error_envelope_from_client(request_call)
        assert envelope.error_class == expected_class
        assert_envelope_shape(envelope)


@pytest.mark.api_tc("020")
def test_api_tc_020_errors_exclude_secrets_and_stack_traces() -> None:
    """API-TC-020: Envelope excludes stack traces and secrets (MOD-API-INV-011, ACD-FR-031)."""
    from dataclasses import fields

    envelope = ApiInternalError(
        "wrapped failure",
        details={"cause": "secret-token-value"},
    ).to_envelope()
    serialized = {
        field.name: getattr(envelope, field.name) for field in fields(ApiErrorEnvelope)
    }

    assert "stack" not in serialized
    assert "traceback" not in serialized
    assert all(
        "Traceback" not in str(value)
        for value in serialized.values()
        if isinstance(value, str)
    )
    assert len(envelope.message) <= 512


@pytest.mark.api_tc("021")
def test_api_tc_021_missing_workflow_id_on_scoped_route_rejected(
    api_router_under_test,
    fake_workflow_engine,
    api_deps,
) -> None:
    """API-TC-021: Empty workflow_id path rejected with validation envelope (ACD-INT-009)."""
    deps = ApiDependencies(
        config=api_deps.config,
        workflow_engine=fake_workflow_engine,
        readiness_probes=api_deps.readiness_probes,
    )
    invalid_ids = ("", "   ")

    for workflow_id in invalid_ids:
        with pytest.raises(ApiValidationError):
            run_async(
                handle_get_workflow_status(deps=deps, workflow_id=workflow_id),
            )
        with pytest.raises(ApiValidationError):
            run_async(
                handle_get_workflow_history(deps=deps, workflow_id=workflow_id),
            )

    router = api_router_under_test(engine=fake_workflow_engine)
    client = make_test_client(router)
    blank_id = "%20"

    for path in (
        f"/workflows/{blank_id}",
        f"/workflows/{blank_id}/history",
        f"/workflows/{blank_id}/output",
        f"/workflows/{blank_id}/timeline",
        f"/workflows/{blank_id}/approval",
    ):
        if path.endswith("/approval"):
            response = client.post(path, json={"action": "APPROVE"})
        else:
            response = client.get(path)
        assert response.status_code == 400
        envelope = ApiErrorEnvelope(**response.json())
        assert envelope.error_class == "API_VALIDATION"


@pytest.mark.api_tc("022")
def test_api_tc_022_no_forbidden_imports_in_api_package() -> None:
    """API-TC-022: Static import analysis — no forbidden module imports (MOD-API-INV-001)."""
    api_src = Path(__file__).resolve().parents[3] / "src" / "api"
    violations: list[str] = []

    for py_file in api_src.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in _FORBIDDEN_IMPORT_PREFIXES:
                        violations.append(f"{py_file.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in _FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(f"{py_file.name}: from {node.module}")

    assert violations == []


@pytest.mark.api_tc("023")
def test_api_tc_023_request_response_types_match_interfaces() -> None:
    """API-TC-023: REST DTO fields match interfaces.md §3 (M1 executable surface)."""
    dto_types = (
        InitiateWorkflowApiRequest,
        InitiateWorkflowApiResponse,
        WorkflowStatusResponse,
        TransitionRecordResponse,
        WorkflowHistoryResponse,
        WorkflowOutputResponse,
        SubmitApprovalApiRequest,
        SubmitApprovalApiResponse,
        TimelineEventResponse,
        WorkflowTimelineResponse,
        HealthResponse,
        DependencyCheck,
        ReadinessResponse,
        ApiErrorEnvelope,
    )
    for dto_type in dto_types:
        dto_field_names_match_interfaces(dto_type)


def _route_pairs_from_router(router: object) -> list[tuple[str, str]]:
    from .helpers import extract_registered_routes

    return extract_registered_routes(router)
