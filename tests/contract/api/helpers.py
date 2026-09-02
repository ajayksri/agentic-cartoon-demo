"""Shared contract-test helpers for api module (API-017, LLD §14)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

import pytest

from config import (
    AgentConfig,
    AgentId,
    AppConfig,
    BackoffConfig,
    CollectionConfig,
    FailureInjectionConfig,
    InfrastructureConfig,
    PostgresConfig,
    ProviderConfig,
    ProviderId,
    RedisConfig,
    RetryPolicy,
    TaskType,
    WorkerConfig,
    WorkflowConfig,
)
from workflow import (
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowResult,
    InvalidApprovalActionError,
    TimelineEvent,
    TransitionRecord,
    WorkflowHistory,
    WorkflowNotFoundError,
    WorkflowOutput,
    WorkflowState,
    WorkflowStatus,
    WorkflowTerminalError,
    WorkflowTimeline,
)

from api import (
    ApiDependencies,
    ApiErrorEnvelope,
    DependencyCheck,
    DependencyCheckStatus,
    InitiateWorkflowApiRequest,
    PATH_HEALTH,
    PATH_READY,
    PATH_WORKFLOW_APPROVAL,
    PATH_WORKFLOW_BY_ID,
    PATH_WORKFLOW_HISTORY,
    PATH_WORKFLOW_OUTPUT,
    PATH_WORKFLOW_TIMELINE,
    PATH_WORKFLOWS,
    ROUTE_APPROVAL,
    ROUTE_HEALTH,
    ROUTE_HISTORY,
    ROUTE_INITIATE,
    ROUTE_OUTPUT,
    ROUTE_READY,
    ROUTE_STATUS,
    ROUTE_TIMELINE,
    SubmitApprovalApiRequest,
    map_workflow_error,
)

_EXPECTED_ROUTE_BINDINGS: tuple[tuple[str, str, str], ...] = (
    (ROUTE_INITIATE, "POST", PATH_WORKFLOWS),
    (ROUTE_STATUS, "GET", PATH_WORKFLOW_BY_ID),
    (ROUTE_HISTORY, "GET", PATH_WORKFLOW_HISTORY),
    (ROUTE_OUTPUT, "GET", PATH_WORKFLOW_OUTPUT),
    (ROUTE_APPROVAL, "POST", PATH_WORKFLOW_APPROVAL),
    (ROUTE_TIMELINE, "GET", PATH_WORKFLOW_TIMELINE),
    (ROUTE_HEALTH, "GET", PATH_HEALTH),
    (ROUTE_READY, "GET", PATH_READY),
)

_INTERFACE_DTO_FIELDS: dict[str, tuple[str, ...]] = {
    "InitiateWorkflowApiRequest": ("workflow_id", "correlation_id", "actor"),
    "InitiateWorkflowApiResponse": (
        "workflow_id",
        "state",
        "state_version",
        "created_at",
        "trace_id",
    ),
    "WorkflowStatusResponse": (
        "workflow_id",
        "state",
        "state_version",
        "created_at",
        "updated_at",
        "revision_count",
        "failure_reason",
    ),
    "TransitionRecordResponse": (
        "transition_id",
        "from_state",
        "to_state",
        "reason",
        "occurred_at",
        "actor",
    ),
    "WorkflowHistoryResponse": ("workflow_id", "transitions"),
    "WorkflowOutputResponse": (
        "workflow_id",
        "state",
        "package",
        "is_complete",
        "failure_reason",
    ),
    "SubmitApprovalApiRequest": ("action", "actor", "idempotency_key"),
    "SubmitApprovalApiResponse": (
        "workflow_id",
        "action",
        "from_state",
        "to_state",
        "state_version",
        "transition_id",
    ),
    "TimelineEventResponse": (
        "occurred_at",
        "event_type",
        "summary",
        "state",
        "task_type",
        "attributes",
    ),
    "WorkflowTimelineResponse": ("workflow_id", "events"),
    "HealthResponse": ("status", "service_name", "timestamp"),
    "DependencyCheck": ("name", "status", "detail"),
    "ReadinessResponse": ("status", "checks", "timestamp"),
    "ApiErrorEnvelope": (
        "error_class",
        "message",
        "retryable",
        "workflow_id",
        "details",
    ),
}


def minimal_app_config(*, max_scenario_revisions: int = 2) -> AppConfig:
    """Valid AppConfig for api contract fixtures."""
    return AppConfig(
        infrastructure=InfrastructureConfig(
            postgres=PostgresConfig(
                host="localhost",
                port=5432,
                database="test",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisConfig(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentConfig(
                provider=ProviderId.GEMINI,
                model="gemini-pro",
                prompt_file="prompts/topic_selector/v1.txt",
            ),
        },
        providers={
            ProviderId.GEMINI: ProviderConfig(
                api_key_env="GEMINI_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionConfig(candidate_count=10, scoring=None),
        workflow=WorkflowConfig(max_scenario_revisions=max_scenario_revisions),
        workers=WorkerConfig(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(
                    initial_seconds=1.0,
                    multiplier=2.0,
                    max_seconds=30.0,
                ),
            ),
        },
        timeouts={},
        failure_injection=FailureInjectionConfig(enabled=False, active_injections=[]),
    )


def load_fakes() -> tuple[type, type]:
    """Load api.fakes doubles (LLD §14 allowlist)."""
    from api.fakes.probes import FakeReadinessProbe
    from api.fakes.workflow import FakeWorkflowEngine

    return FakeWorkflowEngine, FakeReadinessProbe


def default_readiness_probes() -> tuple[Any, ...]:
    """Single healthy postgres probe per LLD §14 fixture helper."""
    _engine_cls, probe_cls = load_fakes()
    return (probe_cls("postgres", ok=True),)


def build_health_dependencies() -> ApiDependencies:
    """ApiDependencies for liveness-only tests without api.fakes (API-TC-017)."""

    class _StubWorkflowEngine:
        """Placeholder until FakeWorkflowEngine is implemented (API-016)."""

    return ApiDependencies(
        config=minimal_app_config(),
        workflow_engine=_StubWorkflowEngine(),  # type: ignore[arg-type]
        readiness_probes=(),
    )


def build_api_dependencies(
    *,
    engine: Any | None = None,
    readiness_probes: tuple[Any, ...] | None = None,
) -> ApiDependencies:
    """Construct ApiDependencies for handler-level contract tests."""
    engine_cls, _probe_cls = load_fakes()
    return ApiDependencies(
        config=minimal_app_config(),
        workflow_engine=engine or engine_cls(),
        readiness_probes=readiness_probes or default_readiness_probes(),
    )


def run_async(coro: Any) -> Any:
    """Run async handler coroutine in contract tests."""
    return asyncio.run(coro)


def make_test_client(router: object) -> Any:
    """Build FastAPI TestClient for wired router (CG-API-007)."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)  # type: ignore[arg-type]
    return TestClient(app)


def extract_registered_routes(router: object) -> list[tuple[str, str]]:
    """Return (method, path) pairs from a FastAPI APIRouter."""
    routes: list[tuple[str, str]] = []
    for route in getattr(router, "routes", ()):
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append((method, path))
    return routes


def assert_envelope_shape(envelope: ApiErrorEnvelope) -> None:
    """Assert ApiErrorEnvelope includes required fields (ACD-API-008)."""
    assert envelope.error_class
    assert envelope.message
    assert envelope.retryable is None or isinstance(envelope.retryable, bool)


def workflow_not_found_envelope(workflow_id: str = "wf-missing") -> ApiErrorEnvelope:
    """Map WorkflowNotFoundError via public api helper."""
    return map_workflow_error(
        WorkflowNotFoundError("workflow not found", workflow_id=workflow_id),
    )


def invalid_approval_envelope(
    workflow_id: str = "wf-wrong-state",
) -> ApiErrorEnvelope:
    """Map InvalidApprovalActionError via public api helper."""
    return map_workflow_error(
        InvalidApprovalActionError(
            "invalid approval",
            workflow_id=workflow_id,
            action=ApprovalAction.APPROVE,
            current_state=WorkflowState.COLLECTING,
        ),
    )


def terminal_workflow_envelope(workflow_id: str = "wf-terminal") -> ApiErrorEnvelope:
    """Map WorkflowTerminalError via public api helper."""
    return map_workflow_error(
        WorkflowTerminalError(
            "terminal workflow",
            workflow_id=workflow_id,
            state=WorkflowState.APPROVED,
        ),
    )


def valid_approval_request(**kwargs: Any) -> SubmitApprovalApiRequest:
    """Build valid approval request using workflow enum (helpers boundary)."""
    return SubmitApprovalApiRequest(action=ApprovalAction.APPROVE, **kwargs)


def empty_workflow_history(*, workflow_id: str) -> WorkflowHistory:
    return WorkflowHistory(workflow_id=workflow_id, transitions=())


def workflow_not_found_error(*, workflow_id: str) -> WorkflowNotFoundError:
    return WorkflowNotFoundError("missing", workflow_id=workflow_id)


def invalid_approval_error(*, workflow_id: str) -> InvalidApprovalActionError:
    return InvalidApprovalActionError(
        "wrong state",
        workflow_id=workflow_id,
        action=ApprovalAction.APPROVE,
        current_state=WorkflowState.COLLECTING,
    )


def terminal_workflow_error(*, workflow_id: str) -> WorkflowTerminalError:
    return WorkflowTerminalError(
        "already terminal",
        workflow_id=workflow_id,
        state=WorkflowState.APPROVED,
    )


_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def sample_transition(
    *,
    transition_id: str,
    from_state: WorkflowState,
    to_state: WorkflowState,
    occurred_at: datetime,
    reason: str = "test_transition",
) -> TransitionRecord:
    return TransitionRecord(
        transition_id=transition_id,
        workflow_id="wf-contract",
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        occurred_at=occurred_at,
        actor="contract-test",
    )


def sample_initiate_result(*, workflow_id: str = "wf-new") -> InitiateWorkflowResult:
    transition = sample_transition(
        transition_id="tr-init",
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COLLECTING,
        occurred_at=_FIXED_NOW,
        reason="workflow_initiated",
    )
    from workflow import OutboxTaskSpec

    return InitiateWorkflowResult(
        workflow_id=workflow_id,
        state=WorkflowState.COLLECTING,
        state_version=1,
        transition=transition,
        enqueued_task=OutboxTaskSpec(
            task_id="task-1",
            workflow_id=workflow_id,
            task_type=TaskType.COLLECT,
            attempt=1,
            payload_reference="payload-ref",
            idempotency_key=f"{workflow_id}:COLLECT:1",
            created_at=_FIXED_NOW,
        ),
    )


def sample_workflow_status(*, workflow_id: str = "wf-status") -> WorkflowStatus:
    return WorkflowStatus(
        workflow_id=workflow_id,
        state=WorkflowState.COLLECTING,
        state_version=2,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        revision_count=0,
        failure_reason=None,
    )


def sample_workflow_history(*, workflow_id: str = "wf-history") -> WorkflowHistory:
    first = sample_transition(
        transition_id="tr-1",
        from_state=WorkflowState.CREATED,
        to_state=WorkflowState.COLLECTING,
        occurred_at=_FIXED_NOW,
    )
    second = sample_transition(
        transition_id="tr-2",
        from_state=WorkflowState.COLLECTING,
        to_state=WorkflowState.COLLECTED,
        occurred_at=datetime(2026, 8, 31, 12, 5, 0, tzinfo=UTC),
    )
    return WorkflowHistory(workflow_id=workflow_id, transitions=(first, second))


def sample_workflow_output(
    *,
    workflow_id: str = "wf-output",
    is_complete: bool,
) -> WorkflowOutput:
    return WorkflowOutput(
        workflow_id=workflow_id,
        state=WorkflowState.APPROVED if is_complete else WorkflowState.FAILED,
        package={"topic": "demo", "scenario": "script"},
        is_complete=is_complete,
        failure_reason=None if is_complete else "generation incomplete",
    )


def sample_approval_result(*, workflow_id: str = "wf-approve") -> ApprovalActionResult:
    transition = sample_transition(
        transition_id="tr-approve",
        from_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        to_state=WorkflowState.APPROVED,
        occurred_at=_FIXED_NOW,
        reason="human_approved",
    )
    return ApprovalActionResult(
        workflow_id=workflow_id,
        action=ApprovalAction.APPROVE,
        from_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        to_state=WorkflowState.APPROVED,
        state_version=5,
        transition_id=transition.transition_id,
        transition=transition,
        enqueued_task=None,
    )


def sample_workflow_timeline(*, workflow_id: str = "wf-timeline") -> WorkflowTimeline:
    events = (
        TimelineEvent(
            occurred_at=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
            event_type="transition",
            summary="created",
            state=WorkflowState.COLLECTING,
        ),
        TimelineEvent(
            occurred_at=datetime(2026, 8, 31, 12, 10, 0, tzinfo=UTC),
            event_type="task_enqueued",
            summary="collect enqueued",
            state=WorkflowState.COLLECTING,
            task_type=TaskType.COLLECT,
        ),
        TimelineEvent(
            occurred_at=datetime(2026, 8, 31, 12, 5, 0, tzinfo=UTC),
            event_type="transition",
            summary="collected",
            state=WorkflowState.COLLECTED,
        ),
    )
    return WorkflowTimeline(workflow_id=workflow_id, events=events)


def configure_engine(
    engine: Any,
    *,
    initiate_result: InitiateWorkflowResult | None = None,
    status: WorkflowStatus | None = None,
    history: WorkflowHistory | None = None,
    output: WorkflowOutput | None = None,
    approval_result: ApprovalActionResult | None = None,
    timeline: WorkflowTimeline | None = None,
    status_error: Exception | None = None,
    approval_error: Exception | None = None,
) -> None:
    """Program FakeWorkflowEngine returns/exceptions for contract scenarios."""
    if initiate_result is not None:
        engine.set_initiate_return(initiate_result)
    if status is not None:
        engine.set_status_return(status)
    if history is not None:
        engine.set_history_return(history)
    if output is not None:
        engine.set_output_return(output)
    if approval_result is not None:
        engine.set_approval_return(approval_result)
    if timeline is not None:
        engine.set_timeline_return(timeline)
    if status_error is not None:
        engine.set_status_error(status_error)
    if approval_error is not None:
        engine.set_approval_error(approval_error)


def dto_field_names_match_interfaces(dto_type: type) -> None:
    """Assert REST DTO fields match interfaces.md §3 (API-TC-023)."""
    expected = _INTERFACE_DTO_FIELDS[dto_type.__name__]
    actual = tuple(field.name for field in fields(dto_type))
    assert actual == expected


def mixed_readiness_probes() -> tuple[Any, ...]:
    """Postgres ok, redis fail — CG-API-003 readiness scenario."""
    _engine_cls, probe_cls = load_fakes()
    return (
        probe_cls("postgres", ok=True),
        probe_cls("redis", ok=False),
    )


def assert_readiness_dependency_checks(
    checks: tuple[DependencyCheck, ...],
) -> None:
    names = {check.name for check in checks}
    assert "postgres" in names
    assert "redis" in names
    by_name = {check.name: check for check in checks}
    assert by_name["postgres"].status == DependencyCheckStatus.OK
    assert by_name["redis"].status == DependencyCheckStatus.FAIL


def assert_initiate_trace_observability(
    *,
    response_body: dict[str, object],
    recording_telemetry: Any,
    workflow_id: str,
) -> None:
    """Assert initiate success records trace_id and root span (API-TC-004)."""
    assert response_body.get("trace_id")
    assert recording_telemetry.span_names, "expected at least one span"
    assert any("initiate" in name for name in recording_telemetry.span_names)
    workflow_span = next(
        (
            event
            for event in recording_telemetry.log_events
            if event.fields.get("workflow_id") == workflow_id
        ),
        None,
    )
    assert workflow_span is not None or workflow_id in str(recording_telemetry.metrics)


def http_error_envelope_from_client(callable_request: Callable[[], Any]) -> ApiErrorEnvelope:
    """Execute TestClient call and parse ApiErrorEnvelope body."""
    response = callable_request()
    assert response.status_code >= 400
    return ApiErrorEnvelope(**response.json())


def call_with_engine_count_guard(
    engine: Any,
    action: Callable[[], None],
) -> int:
    """Return engine call count delta around action (API-TC-005)."""
    before = engine.total_call_count()
    action()
    return engine.total_call_count() - before
