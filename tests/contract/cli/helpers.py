"""Shared contract-test helpers for cli module (CLI-023, LLD §14)."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any

from api.types import (
    ApiErrorEnvelope,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiResponse,
    TimelineEventResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)
from config.types import FailureInjectionConfig, InjectionId, AppConfig
from workflow.types import ApprovalAction, WorkflowState

from cli import (
    ApiClient,
    CliApiError,
    CliClientConfig,
    CliCommandContext,
    CliConfigOverride,
    CliDependencies,
    CliExitCode,
    CliFailureInjectionOverride,
    SubcommandId,
    build_default_subcommand_registry,
    map_api_error_envelope,
    merge_cli_config_override,
    merge_failure_injection_override,
)

_EXPECTED_SUBCOMMAND_IDS: tuple[SubcommandId, ...] = (
    SubcommandId.INITIATE,
    SubcommandId.STATUS,
    SubcommandId.HISTORY,
    SubcommandId.OUTPUT,
    SubcommandId.TIMELINE,
    SubcommandId.APPROVE,
)

_INTERFACE_CONFIG_OVERRIDE_FIELDS: dict[str, tuple[str, ...]] = {
    "CliFailureInjectionOverride": ("enabled", "active_injections"),
    "CliConfigOverride": ("failure_injection",),
}

_INTERFACE_API_CLIENT_METHODS: tuple[str, ...] = (
    "base_url",
    "initiate_workflow",
    "get_workflow_status",
    "get_workflow_history",
    "get_workflow_output",
    "get_workflow_timeline",
    "submit_approval",
    "health_check",
)

_INTERFACE_API_CLIENT_PARAM_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "initiate_workflow": (("request",), ("trace_context",)),
    "get_workflow_status": (("workflow_id",), ()),
    "get_workflow_history": (("workflow_id",), ()),
    "get_workflow_output": (("workflow_id",), ()),
    "get_workflow_timeline": (("workflow_id",), ()),
    "submit_approval": (("workflow_id", "request"), ()),
    "health_check": ((), ()),
}

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def expected_subcommand_ids() -> tuple[SubcommandId, ...]:
    """Return all six V1 subcommand ids (CLI-TC-001)."""
    return _EXPECTED_SUBCOMMAND_IDS


def load_fakes() -> tuple[type, type]:
    """Load cli.fakes doubles (LLD §14 allowlist)."""
    from cli.fakes.api_client import FakeApiClient
    from cli.fakes.logger import RecordingLogger

    return FakeApiClient, RecordingLogger


def minimal_client_config() -> CliClientConfig:
    """Valid CliClientConfig for contract fixtures."""
    return CliClientConfig(api_base_url="http://test")


def minimal_failure_injection_config(*, enabled: bool = False) -> FailureInjectionConfig:
    """Base failure injection config for merge tests."""
    return FailureInjectionConfig(enabled=enabled, active_injections=frozenset())


def build_cli_dependencies(
    *,
    api_client: Any | None = None,
    registry: Any | None = None,
    logger: Any | None = None,
    telemetry: Any | None = None,
) -> CliDependencies:
    """Construct CliDependencies for handler-level contract tests."""
    _client_cls, logger_cls = load_fakes()
    resolved_logger = logger or logger_cls()
    deps_for_registry = CliDependencies(
        client_config=minimal_client_config(),
        registry=_empty_registry_placeholder(),
        logger=resolved_logger,
    )
    resolved_registry = registry or build_default_subcommand_registry(
        deps=deps_for_registry,
        telemetry=telemetry,
    )
    resolved_deps = CliDependencies(
        client_config=minimal_client_config(),
        registry=resolved_registry,
        logger=resolved_logger,
    )
    return resolved_deps


def _empty_registry_placeholder() -> Any:
    """Placeholder until build_default_subcommand_registry is wired."""
    from cli.types import SubcommandRegistry

    return SubcommandRegistry(specs={}, handlers={})


def run_async(coro: Any) -> Any:
    """Run async ApiClient coroutine in contract tests."""
    return asyncio.run(coro)


def sample_initiate_response(*, workflow_id: str = "wf-init-001") -> InitiateWorkflowApiResponse:
    return InitiateWorkflowApiResponse(
        workflow_id=workflow_id,
        state=WorkflowState.COLLECTING,
        state_version=1,
        created_at=_FIXED_NOW,
        trace_id="trace-contract",
    )


def sample_status_response(*, workflow_id: str = "wf-status") -> WorkflowStatusResponse:
    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        state=WorkflowState.COLLECTING,
        state_version=2,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
        revision_count=0,
        failure_reason=None,
    )


def sample_history_response(*, workflow_id: str = "wf-history") -> WorkflowHistoryResponse:
    return WorkflowHistoryResponse(workflow_id=workflow_id, transitions=())


def sample_output_response(*, workflow_id: str = "wf-output") -> WorkflowOutputResponse:
    return WorkflowOutputResponse(
        workflow_id=workflow_id,
        state=WorkflowState.COLLECTED,
        package={"topic": "demo"},
        is_complete=False,
        failure_reason=None,
    )


def sample_timeline_response(*, workflow_id: str = "wf-timeline") -> WorkflowTimelineResponse:
    events = (
        TimelineEventResponse(
            occurred_at=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
            event_type="transition",
            summary="created",
            state=WorkflowState.COLLECTING,
        ),
        TimelineEventResponse(
            occurred_at=datetime(2026, 8, 31, 12, 10, 0, tzinfo=UTC),
            event_type="task_enqueued",
            summary="collect enqueued",
            state=WorkflowState.COLLECTING,
        ),
        TimelineEventResponse(
            occurred_at=datetime(2026, 8, 31, 12, 5, 0, tzinfo=UTC),
            event_type="transition",
            summary="collected",
            state=WorkflowState.COLLECTED,
        ),
    )
    return WorkflowTimelineResponse(workflow_id=workflow_id, events=events)


def sample_approval_response(*, workflow_id: str = "wf-approve") -> SubmitApprovalApiResponse:
    return SubmitApprovalApiResponse(
        workflow_id=workflow_id,
        action=ApprovalAction.APPROVE,
        from_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        to_state=WorkflowState.APPROVED,
        state_version=5,
        transition_id="tr-approve",
    )


def workflow_not_found_envelope(*, workflow_id: str = "wf-missing") -> ApiErrorEnvelope:
    return ApiErrorEnvelope(
        error_class="WF_NOT_FOUND",
        message="workflow not found",
        retryable=False,
        workflow_id=workflow_id,
    )


def invalid_approval_envelope(*, workflow_id: str = "wf-invalid") -> ApiErrorEnvelope:
    return ApiErrorEnvelope(
        error_class="WF_INVALID_APPROVAL",
        message="invalid approval action",
        retryable=False,
        workflow_id=workflow_id,
    )


def configure_fake_api_client(
    client: Any,
    *,
    initiate_response: InitiateWorkflowApiResponse | None = None,
    status_response: WorkflowStatusResponse | None = None,
    history_response: WorkflowHistoryResponse | None = None,
    output_response: WorkflowOutputResponse | None = None,
    timeline_response: WorkflowTimelineResponse | None = None,
    approval_response: SubmitApprovalApiResponse | None = None,
    status_error: Exception | None = None,
    approval_error: Exception | None = None,
    connection_error: Exception | None = None,
) -> None:
    """Program FakeApiClient returns/exceptions for contract scenarios."""
    if initiate_response is not None:
        client.set_initiate_return(initiate_response)
    if status_response is not None:
        client.set_status_return(status_response)
    if history_response is not None:
        client.set_history_return(history_response)
    if output_response is not None:
        client.set_output_return(output_response)
    if timeline_response is not None:
        client.set_timeline_return(timeline_response)
    if approval_response is not None:
        client.set_approval_return(approval_response)
    if status_error is not None:
        client.set_status_error(status_error)
    if approval_error is not None:
        client.set_approval_error(approval_error)
    if connection_error is not None:
        client.set_connection_error(connection_error)


def api_client_call_count(client: Any) -> int:
    """Return recorded FakeApiClient invocation count."""
    return client.total_call_count()


def assert_timeline_stdout_order(stdout: str, *, summaries: Sequence[str]) -> None:
    """Assert timeline summaries appear in chronological order in stdout (CLI-TC-008)."""
    positions = [stdout.index(summary) for summary in summaries]
    assert positions == sorted(positions)


def assert_error_message_excludes_secrets() -> None:
    """Assert mapped CLI errors exclude credential values (CLI-TC-016)."""
    envelope = ApiErrorEnvelope(
        error_class="API_INTERNAL",
        message="request failed",
        retryable=False,
        workflow_id="wf-secret",
        details={"api_key": "super-secret-token", "password": "hunter2"},
    )
    error = map_api_error_envelope(envelope, http_status=500)
    rendered = str(error)
    assert "super-secret-token" not in rendered
    assert "hunter2" not in rendered
    assert error.workflow_id == "wf-secret"


def assert_cli_api_error_from_envelope(
    envelope: ApiErrorEnvelope,
    *,
    workflow_id: str,
) -> CliApiError:
    """Map envelope and assert CliApiError fields (CLI-TC-006, CLI-TC-014)."""
    error = map_api_error_envelope(envelope, http_status=404)
    assert isinstance(error, CliApiError)
    assert error.exit_code == CliExitCode.ERROR
    assert workflow_id in str(error) or error.workflow_id == workflow_id
    assert envelope.error_class in (error.api_error_class, str(error))
    return error


def config_override_field_names_match_interfaces(dto_type: type) -> None:
    """Assert config override DTO fields match interfaces.md §5 (CLI-TC-022)."""
    expected = _INTERFACE_CONFIG_OVERRIDE_FIELDS[dto_type.__name__]
    actual = tuple(field.name for field in fields(dto_type))
    assert actual == expected


def api_client_methods_match_interfaces(protocol_type: type) -> None:
    """Assert ApiClient protocol signatures match interfaces.md §6 (CLI-TC-021)."""
    for method_name in _INTERFACE_API_CLIENT_METHODS:
        assert hasattr(protocol_type, method_name), f"missing ApiClient.{method_name}"
        if method_name == "base_url":
            prop = inspect.getattr_static(protocol_type, method_name)
            assert isinstance(prop, property)
            assert prop.fget is not None
            sig = inspect.signature(prop.fget)
            assert sig.return_annotation is str or sig.return_annotation == "str"
            continue

        member = getattr(protocol_type, method_name)
        assert callable(member) or inspect.iscoroutinefunction(member)
        sig = inspect.signature(member)
        expected_pos, expected_kw = _INTERFACE_API_CLIENT_PARAM_SPECS[method_name]
        positional = [
            param.name
            for param in sig.parameters.values()
            if param.name != "self"
            and param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY,
            )
        ]
        keyword_only = [
            param.name
            for param in sig.parameters.values()
            if param.kind == inspect.Parameter.KEYWORD_ONLY
        ]
        assert tuple(positional) == expected_pos, f"{method_name} positional params"
        assert tuple(keyword_only) == expected_kw, f"{method_name} keyword-only params"
        assert sig.return_annotation is not inspect.Signature.empty


def run_handler_with_context(
    handler: Any,
    *,
    subcommand_id: SubcommandId,
    workflow_id: str | None,
    api_client: ApiClient,
    logger: Any,
    raw_args: tuple[str, ...] = (),
) -> Any:
    """Invoke subcommand handler with CliCommandContext."""
    ctx = CliCommandContext(
        subcommand_id=subcommand_id,
        workflow_id=workflow_id,
        api_client=api_client,
        logger=logger,
        raw_args=raw_args,
    )
    return handler.run(ctx=ctx)


def call_with_api_client_count_guard(
    client: Any,
    action: Callable[[], None],
) -> int:
    """Return FakeApiClient call count delta around action (CLI-TC-004)."""
    before = api_client_call_count(client)
    action()
    return api_client_call_count(client) - before


def enabled_injection_override(
    *injection_ids: str,
) -> CliFailureInjectionOverride:
    """Build enabled CliFailureInjectionOverride for merge tests."""
    return CliFailureInjectionOverride(
        enabled=True,
        active_injections=frozenset(injection_ids),
    )


def assert_merged_injection_active(*, injection_id: str) -> None:
    """Assert merge enables the requested injection id (CLI-TC-012)."""
    base = _minimal_app_config_for_merge()
    override = CliConfigOverride(failure_injection=enabled_injection_override(injection_id))
    merged = merge_cli_config_override(base, override)
    assert merged.is_injection_active(InjectionId(injection_id)) is True


@dataclass(frozen=True, slots=True)
class _MergeTestAppConfig(AppConfig):
    """Minimal AppConfig double supporting merge_cli_config_override + is_injection_active."""

    def is_injection_active(self, injection_id: InjectionId) -> bool:
        if not self.failure_injection.enabled:
            return False
        return injection_id in self.failure_injection.active_injections


def _minimal_app_config_for_merge() -> AppConfig:
    """Minimal validated AppConfig for CLI merge contract tests."""
    from config.types import (
        AgentConfig,
        AgentId,
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

    return _MergeTestAppConfig(
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
                prompt_file="prompts/topic_selector.txt",
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
        workflow=WorkflowConfig(max_scenario_revisions=2),
        workers=WorkerConfig(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={
            TaskType.COLLECT: RetryPolicy(
                max_attempts=3,
                backoff=BackoffConfig(1.0, 2.0, 30.0),
            ),
        },
        timeouts={},
        failure_injection=FailureInjectionConfig(enabled=False, active_injections=frozenset()),
    )
