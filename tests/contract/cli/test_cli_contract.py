"""Contract tests CLI-TC-001 through CLI-TC-022 (CLI-023).

Imports ONLY from the cli package public surface (`cli.__init__`).
Boundary imports for fixture injection live in helpers.py / conftest.py per LLD §14.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from cli import (
    ApiClient,
    CliApiError,
    CliClientConfig,
    CliConfigError,
    CliConfigOverride,
    CliConnectionError,
    CliDependencies,
    CliError,
    CliExitCode,
    CliFailureInjectionOverride,
    CliUsageError,
    SubcommandId,
    SubcommandRegistry,
    SubcommandSpec,
    build_default_subcommand_registry,
    create_cli_app,
    merge_cli_config_override,
    merge_failure_injection_override,
    parse_failure_injection_flags,
)

from .helpers import (
    assert_merged_injection_active,
    api_client_methods_match_interfaces,
    assert_error_message_excludes_secrets,
    assert_timeline_stdout_order,
    call_with_api_client_count_guard,
    configure_fake_api_client,
    expected_subcommand_ids,
    invalid_approval_envelope,
    minimal_failure_injection_config,
    sample_approval_response,
    sample_history_response,
    sample_initiate_response,
    sample_output_response,
    sample_status_response,
    sample_timeline_response,
    workflow_not_found_envelope,
    config_override_field_names_match_interfaces,
)

# Contract tests active after CLI-023 implementation.

_FORBIDDEN_IMPORT_PREFIXES = (
    "worker",
    "agents",
    "workflow",
    "persistence",
    "task_queue",
)

_PUBLIC_EXPORTS: tuple[str, ...] = (
    "run_cli",
    "create_cli_app",
    "CliApp",
    "CliDependencies",
    "create_api_client",
    "ApiClient",
    "build_default_subcommand_registry",
    "SubcommandRegistry",
    "SubcommandSpec",
    "SubcommandHandler",
    "SubcommandId",
    "CliCommandContext",
    "CliCommandResult",
    "CliClientConfig",
    "CliExitCode",
    "CliConfigOverride",
    "CliFailureInjectionOverride",
    "parse_failure_injection_flags",
    "merge_failure_injection_override",
    "merge_cli_config_override",
    "CliError",
    "CliUsageError",
    "CliApiError",
    "CliConnectionError",
    "CliConfigError",
    "map_api_error_envelope",
)


@pytest.mark.cli_tc("001")
def test_cli_tc_001_default_registry_exposes_all_subcommand_specs(
    fake_api_client,
    recording_logger,
) -> None:
    """CLI-TC-001: build_default_subcommand_registry registers six specs (MOD-CLI-INV-004)."""
    deps = CliDependencies(
        client_config=CliClientConfig(api_base_url="http://test"),
        registry=SubcommandRegistry(specs={}, handlers={}),
        logger=recording_logger,
    )
    registry = build_default_subcommand_registry(deps=deps)

    assert isinstance(registry, SubcommandRegistry)
    registered_ids = set(registry.specs.keys())
    assert registered_ids == set(expected_subcommand_ids())
    for subcommand_id in expected_subcommand_ids():
        spec = registry.get_spec(subcommand_id)
        assert isinstance(spec, SubcommandSpec)
        assert spec.id == subcommand_id
        assert spec.name


@pytest.mark.cli_tc("002")
def test_cli_tc_002_public_types_importable_from_package_root() -> None:
    """CLI-TC-002: Public executable surface exports match interfaces.md §9."""
    import cli

    for symbol in _PUBLIC_EXPORTS:
        assert hasattr(cli, symbol), f"missing export {symbol}"
        assert symbol in cli.__all__

    assert inspect.isclass(CliDependencies)
    assert inspect.isfunction(create_cli_app)
    assert SubcommandId.INITIATE == "initiate"


@pytest.mark.cli_tc("003")
def test_cli_tc_003_initiate_subcommand_returns_workflow_id(
    cli_app_under_test,
    fake_api_client,
    capsys,
) -> None:
    """CLI-TC-003: Initiate prints workflow_id and exits 0 (ACD-CLI-001, MOD-CLI-INV-005)."""
    configure_fake_api_client(
        fake_api_client,
        initiate_response=sample_initiate_response(workflow_id="wf-init-001"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["initiate", "--actor", "contract-test"])

    captured = capsys.readouterr()
    assert exit_code == CliExitCode.SUCCESS
    assert "wf-init-001" in captured.out


@pytest.mark.cli_tc("004")
def test_cli_tc_004_invalid_argv_rejected_without_api_calls(
    cli_app_under_test,
    fake_api_client,
) -> None:
    """CLI-TC-004: Invalid argv raises CliUsageError exit 2; API client not called (ACD-INT-008)."""
    app = cli_app_under_test(api_client=fake_api_client)

    delta = call_with_api_client_count_guard(
        fake_api_client,
        lambda: app.run(["initiate"]),
    )

    assert delta == 0
    exit_code = app.run(["initiate"])
    assert exit_code == CliExitCode.USAGE


@pytest.mark.cli_tc("005")
def test_cli_tc_005_status_renders_workflow_snapshot(
    cli_app_under_test,
    fake_api_client,
    capsys,
) -> None:
    """CLI-TC-005: Status handler prints state on success (ACD-CLI-002, ACD-OPS-006)."""
    configure_fake_api_client(
        fake_api_client,
        status_response=sample_status_response(workflow_id="wf-collecting"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["status", "wf-collecting"])

    captured = capsys.readouterr()
    assert exit_code == CliExitCode.SUCCESS
    assert "COLLECTING" in captured.out


@pytest.mark.cli_tc("006")
def test_cli_tc_006_unknown_workflow_maps_to_cli_api_error(
    cli_app_under_test,
    fake_api_client,
    capsys,
) -> None:
    """CLI-TC-006: WF_NOT_FOUND maps to CliApiError exit 1 with workflow_id (contract §3.2)."""
    envelope = workflow_not_found_envelope(workflow_id="wf-missing")
    configure_fake_api_client(
        fake_api_client,
        status_error=CliApiError(
            envelope.message,
            workflow_id=envelope.workflow_id,
            api_error_class=envelope.error_class,
        ),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["status", "wf-missing"])
    captured = capsys.readouterr()

    assert exit_code == CliExitCode.ERROR
    assert "wf-missing" in captured.err or "wf-missing" in captured.out


@pytest.mark.cli_tc("007")
def test_cli_tc_007_history_and_output_invoke_correct_api_methods(
    cli_app_under_test,
    fake_api_client,
) -> None:
    """CLI-TC-007: History/output call get_workflow_history and get_workflow_output once (ACD-CLI-002)."""
    configure_fake_api_client(
        fake_api_client,
        history_response=sample_history_response(workflow_id="wf-history"),
        output_response=sample_output_response(workflow_id="wf-output"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    app.run(["history", "wf-history"])
    app.run(["output", "wf-output"])

    assert fake_api_client.get_workflow_history_calls == ["wf-history"]
    assert fake_api_client.get_workflow_output_calls == ["wf-output"]


@pytest.mark.cli_tc("008")
def test_cli_tc_008_timeline_output_reflects_event_order(
    cli_app_under_test,
    fake_api_client,
    capsys,
) -> None:
    """CLI-TC-008: Timeline stdout reflects occurred_at ascending order (ACD-FR-066)."""
    configure_fake_api_client(
        fake_api_client,
        timeline_response=sample_timeline_response(workflow_id="wf-timeline-order"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["timeline", "wf-timeline-order"])
    captured = capsys.readouterr()

    assert exit_code == CliExitCode.SUCCESS
    assert_timeline_stdout_order(
        captured.out,
        summaries=("created", "collected", "collect enqueued"),
    )


@pytest.mark.cli_tc("009")
def test_cli_tc_009_parse_failure_injection_flags_returns_override() -> None:
    """CLI-TC-009: parse_failure_injection_flags enables FINJ-WKR-PRE (ACD-CLI-003, CG-CLI-002)."""
    override = parse_failure_injection_flags(["--inject", "FINJ-WKR-PRE"])

    assert override is not None
    assert override.enabled is True
    assert "FINJ-WKR-PRE" in override.active_injections


@pytest.mark.cli_tc("010")
def test_cli_tc_010_unknown_injection_id_rejected_at_parse() -> None:
    """CLI-TC-010: Unknown injection id raises CliUsageError before config load (ACD-CFG-007)."""
    with pytest.raises(CliUsageError):
        parse_failure_injection_flags(["--inject", "FINJ-UNKNOWN"])
    with pytest.raises(CliUsageError):
        merge_failure_injection_override(
            minimal_failure_injection_config(enabled=False),
            CliFailureInjectionOverride(enabled=True, active_injections=frozenset({"FINJ-UNKNOWN"})),
        )


@pytest.mark.cli_tc("011")
def test_cli_tc_011_merge_preserves_base_when_override_none() -> None:
    """CLI-TC-011: merge_failure_injection_override(base, None) unchanged (ACD-SEC-007)."""
    base = minimal_failure_injection_config(enabled=False)

    merged = merge_failure_injection_override(base, None)

    assert merged == base


@pytest.mark.cli_tc("012")
def test_cli_tc_012_merge_activates_selected_injection_ids() -> None:
    """CLI-TC-012: Merge enables FINJ-WKR-PRE on effective config view (ACD-FR-058)."""
    assert_merged_injection_active(injection_id="FINJ-WKR-PRE")


@pytest.mark.cli_tc("013")
def test_cli_tc_013_approve_delegates_to_submit_approval(
    cli_app_under_test,
    fake_api_client,
) -> None:
    """CLI-TC-013: Approve handler calls submit_approval (ACD-CLI-005, ACD-FR-014)."""
    configure_fake_api_client(
        fake_api_client,
        approval_response=sample_approval_response(workflow_id="wf-approve-ok"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["approve", "wf-approve-ok", "--action", "APPROVE"])

    assert exit_code == CliExitCode.SUCCESS
    assert fake_api_client.submit_approval_calls == [("wf-approve-ok", "APPROVE")]


@pytest.mark.cli_tc("014")
def test_cli_tc_014_invalid_approval_maps_to_cli_api_error(
    cli_app_under_test,
    fake_api_client,
    capsys,
) -> None:
    """CLI-TC-014: WF_INVALID_APPROVAL maps to CliApiError exit 1 (ACD-SEC-006)."""
    envelope = invalid_approval_envelope(workflow_id="wf-invalid-approval")
    configure_fake_api_client(
        fake_api_client,
        approval_error=CliApiError(
            envelope.message,
            workflow_id=envelope.workflow_id,
            api_error_class=envelope.error_class,
        ),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["approve", "wf-invalid-approval", "--action", "APPROVE"])
    captured = capsys.readouterr()

    assert exit_code == CliExitCode.ERROR
    assert "WF_INVALID_APPROVAL" in captured.err or envelope.error_class in captured.err


@pytest.mark.cli_tc("015")
def test_cli_tc_015_cli_error_subclasses_expose_code_and_exit_code() -> None:
    """CLI-TC-015: Each CliError subclass exposes stable code and exit_code (ACD-INT-008)."""
    cases: tuple[tuple[type[CliError], str, CliExitCode], ...] = (
        (CliUsageError, "CLI_USAGE", CliExitCode.USAGE),
        (CliApiError, "CLI_API", CliExitCode.ERROR),
        (CliConnectionError, "CLI_CONNECTION", CliExitCode.CONNECTION),
        (CliConfigError, "CLI_CONFIG", CliExitCode.USAGE),
    )
    for error_type, code, exit_code in cases:
        error = error_type("contract test")
        assert error.code == code
        assert error.exit_code == exit_code


@pytest.mark.cli_tc("016")
def test_cli_tc_016_mapped_errors_exclude_secrets() -> None:
    """CLI-TC-016: map_api_error_envelope excludes credential values (MOD-CLI-INV-009)."""
    assert_error_message_excludes_secrets()


@pytest.mark.cli_tc("017")
def test_cli_tc_017_connection_failure_uses_connection_exit_code(
    cli_app_under_test,
    fake_api_client,
) -> None:
    """CLI-TC-017: Transport failure maps to CliConnectionError exit 3 (contract §3.4)."""
    configure_fake_api_client(
        fake_api_client,
        connection_error=CliConnectionError("connection refused"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["status", "wf-offline"])

    assert exit_code == CliExitCode.CONNECTION


@pytest.mark.cli_tc("018")
def test_cli_tc_018_empty_workflow_id_rejected_on_scoped_subcommands(
    cli_app_under_test,
    fake_api_client,
) -> None:
    """CLI-TC-018: Empty workflow_id raises CliUsageError exit 2 (ACD-INT-009, MOD-CLI-INV-006)."""
    app = cli_app_under_test(api_client=fake_api_client)

    for argv in (
        ["status", ""],
        ["history", "   "],
        ["output", ""],
        ["timeline", "   "],
        ["approve", "", "--action", "APPROVE"],
    ):
        exit_code = app.run(argv)
        assert exit_code == CliExitCode.USAGE


@pytest.mark.cli_tc("019")
def test_cli_tc_019_subcommand_emits_started_and_completed_events(
    cli_app_under_test,
    fake_api_client,
    recording_cli_telemetry,
    capsys,
) -> None:
    """CLI-TC-019: Successful initiate logs cli_command_started/completed (ACD-OPS-008)."""
    configure_fake_api_client(
        fake_api_client,
        initiate_response=sample_initiate_response(workflow_id="wf-telemetry"),
    )
    app = cli_app_under_test(api_client=fake_api_client)

    exit_code = app.run(["initiate", "--actor", "contract-test"])
    _ = capsys.readouterr()

    assert exit_code == CliExitCode.SUCCESS
    assert "cli_command_started" in recording_cli_telemetry.event_names
    assert "cli_command_completed" in recording_cli_telemetry.event_names


@pytest.mark.cli_tc("020")
def test_cli_tc_020_no_forbidden_imports_in_cli_package() -> None:
    """CLI-TC-020: Static import analysis — no forbidden module imports (MOD-CLI-INV-001)."""
    cli_src = Path(__file__).resolve().parents[3] / "src" / "cli"
    violations: list[str] = []

    for py_file in cli_src.rglob("*.py"):
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


@pytest.mark.cli_tc("021")
def test_cli_tc_021_api_client_signatures_match_interfaces() -> None:
    """CLI-TC-021: ApiClient protocol methods match interfaces.md §6."""
    api_client_methods_match_interfaces(ApiClient)


@pytest.mark.cli_tc("022")
def test_cli_tc_022_config_override_types_match_interfaces() -> None:
    """CLI-TC-022: Config override types and merge functions match interfaces.md §5."""
    config_override_field_names_match_interfaces(CliFailureInjectionOverride)
    config_override_field_names_match_interfaces(CliConfigOverride)
    assert callable(parse_failure_injection_flags)
    assert callable(merge_failure_injection_override)
    assert callable(merge_cli_config_override)
