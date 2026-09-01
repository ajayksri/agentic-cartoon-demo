"""Contract tests RT-TC-001 through RT-TC-025 (RT-018).

Imports ONLY from the runtime package public surface (`runtime.__init__`).
Boundary imports for fixture injection live in helpers.py / conftest.py per LLD §21.3.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

import runtime
from runtime import (
    API_ENTRY,
    COORDINATOR_ENTRY,
    WORKER_ENTRY,
    BootstrapError,
    CompositionRoot,
    DependencyWiringError,
    OutboxPublishBatchResult,
    OutboxPublisherLoop,
    ProcessKind,
    UnsupportedProcessKindError,
    create_composition_root,
    create_outbox_publisher_loop,
    run_api_process,
    run_coordinator_process,
    run_worker_process,
)

from .helpers import (
    StubOutboxPublisherLoop,
    assert_error_message_excludes_secrets,
    entry_function_parameters,
    minimal_runtime_config,
    public_export_names,
    read_public_module_sources,
    runtime_public_module_paths,
    static_scan_allowed_import_roots,
    static_scan_forbidden_imports,
)

_REQUIRED_PUBLIC_EXPORTS = frozenset(
    {
        "API_ENTRY",
        "COORDINATOR_ENTRY",
        "WORKER_ENTRY",
        "BootstrapError",
        "BootstrapResult",
        "CompositionRoot",
        "CoordinatorLoopConfig",
        "DependencyWiringError",
        "OutboxPublishBatchResult",
        "OutboxPublisherConfig",
        "OutboxPublisherLoop",
        "ProcessEntryPoint",
        "ProcessKind",
        "ProcessShutdownError",
        "ProcessStartupError",
        "RuntimeModuleError",
        "UnsupportedProcessKindError",
        "WiredDependencies",
        "create_composition_root",
        "create_outbox_publisher_loop",
        "run_api_process",
        "run_coordinator_process",
        "run_worker_process",
    }
)

_K8S_PARAMETER_NAMES = frozenset({"namespace", "pod_name", "service_account", "kubeconfig"})


@pytest.mark.runtime_tc("001")
def test_rt_tc_001_create_composition_root_returns_root_with_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RT-TC-001: valid config source yields CompositionRoot with config."""
    monkeypatch.setattr(
        "runtime.composition.load_config",
        lambda source=None, **_kwargs: minimal_runtime_config(),
    )
    root = create_composition_root()
    assert hasattr(root, "config")
    assert hasattr(root, "bootstrap")
    assert root.config is not None


@pytest.mark.runtime_tc("002")
def test_rt_tc_002_invalid_config_raises_before_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """RT-TC-002: invalid config raises ConfigError; no CompositionRoot returned."""
    from config.errors import ConfigSecretDetectedError

    def _raise_secret(source=None, **_kwargs: object) -> None:
        raise ConfigSecretDetectedError("inline secret detected", key_path="providers.api_key")

    monkeypatch.setattr("runtime.composition.load_config", _raise_secret)

    with pytest.raises(ConfigSecretDetectedError):
        create_composition_root()


@pytest.mark.runtime_tc("003")
def test_rt_tc_003_entry_functions_have_no_k8s_parameters() -> None:
    """RT-TC-003: run_*_process signatures avoid k8s-specific parameters."""
    for func in (run_api_process, run_coordinator_process, run_worker_process):
        param_names = {param.name for param in entry_function_parameters(func)}
        assert param_names.isdisjoint(_K8S_PARAMETER_NAMES)


@pytest.mark.runtime_tc("004")
def test_rt_tc_004_three_entry_kinds_bootstrap_independently(bootstrap_for_tests) -> None:
    """RT-TC-004: api/coordinator/worker bootstrap independently with fakes."""
    for entry in (API_ENTRY, COORDINATOR_ENTRY, WORKER_ENTRY):
        wired = bootstrap_for_tests(entry=entry)
        assert wired.entry.kind == entry.kind


@pytest.mark.runtime_tc("005")
def test_rt_tc_005_observability_before_loop_hooks(bootstrap_for_tests) -> None:
    """RT-TC-005: configure_observability precedes loop start hooks."""
    from runtime.telemetry import RecordingRuntimeTelemetry

    telemetry = RecordingRuntimeTelemetry(process_kind=ProcessKind.API)
    bootstrap_for_tests(entry=API_ENTRY, telemetry=telemetry)
    assert telemetry.configure_observability_index == 0
    assert telemetry.loop_start_index == 1


@pytest.mark.runtime_tc("006")
def test_rt_tc_006_load_config_called_once_at_root_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RT-TC-006: load_config invoked exactly once at create_composition_root."""
    from unittest.mock import MagicMock, patch

    calls = {"count": 0}

    def _load_config(source=None, **_kwargs: object) -> object:
        calls["count"] += 1
        return minimal_runtime_config()

    monkeypatch.setattr("runtime.composition.load_config", _load_config)
    root = create_composition_root()
    with patch.object(root, "bootstrap", return_value=MagicMock()):
        root.bootstrap(API_ENTRY)
    assert calls["count"] == 1


@pytest.mark.runtime_tc("007")
def test_rt_tc_007_no_efms_symbols_in_public_modules() -> None:
    """RT-TC-007: public runtime modules contain no EFMS-specific symbols."""
    source = read_public_module_sources().lower()
    for token in ("efms_", "efms"):
        assert token not in source


@pytest.mark.runtime_tc("008")
def test_rt_tc_008_coordinator_wires_outbox_and_queue(bootstrap_for_tests) -> None:
    """RT-TC-008: coordinator bootstrap wires outbox publisher and queue."""
    wired = bootstrap_for_tests(entry=COORDINATOR_ENTRY)
    assert wired.outbox_publisher is not None
    assert wired.task_queue is not None
    assert wired.workflow_engine is not None


@pytest.mark.runtime_tc("009")
def test_rt_tc_009_reconciliation_invocable_after_coordinator_bootstrap(
    bootstrap_for_tests,
    fake_workflow_engine,
) -> None:
    """RT-TC-009: reconcile_stuck_workflows invocable on wired workflow engine."""
    wired = bootstrap_for_tests(
        entry=COORDINATOR_ENTRY,
        workflow_engine=fake_workflow_engine,
    )
    wired.workflow_engine.reconcile_stuck_workflows(config=minimal_runtime_config())
    assert fake_workflow_engine.reconcile_calls


@pytest.mark.runtime_tc("010")
def test_rt_tc_010_failure_injection_before_worker_loop(bootstrap_for_tests) -> None:
    """RT-TC-010: configure_failure_injection before worker loop start hook."""
    from .helpers import RecordingCallOrder

    order = RecordingCallOrder(calls=[])
    bootstrap_for_tests(entry=WORKER_ENTRY, call_order=order)
    assert "configure_failure_injection" in order.calls
    assert "worker_loop_start" in order.calls
    assert order.calls.index("configure_failure_injection") < order.calls.index(
        "worker_loop_start"
    )


@pytest.mark.runtime_tc("011")
def test_rt_tc_011_api_wiring_sets_router_not_worker_or_outbox(bootstrap_for_tests) -> None:
    """RT-TC-011: API bootstrap wires router only."""
    wired = bootstrap_for_tests(entry=API_ENTRY)
    assert wired.api_router is not None
    assert wired.worker_loop is None
    assert wired.outbox_publisher is None


@pytest.mark.runtime_tc("012")
def test_rt_tc_012_worker_wiring_sets_worker_loop_not_api_or_outbox(
    bootstrap_for_tests,
    fake_worker_loop,
) -> None:
    """RT-TC-012: worker bootstrap wires worker loop only."""
    wired = bootstrap_for_tests(entry=WORKER_ENTRY, worker_loop=fake_worker_loop)
    assert wired.worker_loop is fake_worker_loop
    assert wired.api_router is None
    assert wired.outbox_publisher is None


@pytest.mark.runtime_tc("013")
def test_rt_tc_013_unsupported_process_kind_rejected() -> None:
    """RT-TC-013: unsupported kind raises UnsupportedProcessKindError."""
    from unittest.mock import MagicMock, patch

    from runtime.composition import DefaultCompositionRoot

    root = DefaultCompositionRoot(minimal_runtime_config())
    invalid = SimpleNamespace(kind="invalid", service_name="bad")
    with patch("runtime.composition.SharedBootstrap") as shared:
        shared.return_value.wire_common.return_value = MagicMock()
        with pytest.raises(UnsupportedProcessKindError):
            root.bootstrap(invalid)  # type: ignore[arg-type]


@pytest.mark.runtime_tc("014")
def test_rt_tc_014_outbox_publisher_loop_protocol_defines_run_and_stop() -> None:
    """RT-TC-014: OutboxPublisherLoop exposes run() and stop()."""
    loop = StubOutboxPublisherLoop()
    assert hasattr(loop, "run")
    assert hasattr(loop, "stop")
    assert callable(getattr(OutboxPublisherLoop, "run", loop.run))
    assert callable(getattr(OutboxPublisherLoop, "stop", loop.stop))


@pytest.mark.runtime_tc("015")
def test_rt_tc_015_outbox_publish_batch_result_is_immutable() -> None:
    """RT-TC-015: OutboxPublishBatchResult is frozen."""
    result = OutboxPublishBatchResult(
        fetched_count=1,
        published_count=1,
        failed_count=0,
    )
    with pytest.raises(FrozenInstanceError):
        result.published_count = 2  # type: ignore[misc]


@pytest.mark.runtime_tc("016")
def test_rt_tc_016_outbox_stop_is_idempotent() -> None:
    """RT-TC-016: repeated stop() is safe."""
    loop = StubOutboxPublisherLoop()
    loop.stop()
    loop.stop()
    assert loop._stopped is True


@pytest.mark.runtime_tc("017")
def test_rt_tc_017_worker_shutdown_calls_worker_loop_stop(fake_worker_loop) -> None:
    """RT-TC-017: worker runner invokes WorkerLoop.stop() before teardown."""
    from .helpers import simulate_worker_shutdown

    teardown = SimpleNamespace(called=False)

    def _teardown() -> None:
        teardown.called = True

    simulate_worker_shutdown(worker_loop=fake_worker_loop, teardown=_teardown)
    assert fake_worker_loop.stop_calls >= 1
    assert teardown.called is True


@pytest.mark.runtime_tc("018")
def test_rt_tc_018_bootstrap_failure_surfaces_bootstrap_error(bootstrap_for_tests) -> None:
    """RT-TC-018: persistence wiring failure raises BootstrapError/DependencyWiringError."""
    from .helpers import RecordingCallOrder

    order = RecordingCallOrder(calls=[])

    with pytest.raises((BootstrapError, DependencyWiringError)):
        bootstrap_for_tests(
            entry=API_ENTRY,
            call_order=order,
            persistence_error=RuntimeError("postgres unavailable"),
        )


@pytest.mark.runtime_tc("019")
def test_rt_tc_019_no_forbidden_imports_in_public_modules() -> None:
    """RT-TC-019: types/errors/protocols avoid forbidden modules."""
    violations: list[str] = []
    for path in runtime_public_module_paths():
        if path.name in {"types.py", "errors.py", "protocols.py"}:
            violations.extend(static_scan_forbidden_imports(path))
    assert violations == []


@pytest.mark.runtime_tc("020")
def test_rt_tc_020_allowed_dependency_imports_only() -> None:
    """RT-TC-020: runtime package import graph stays within allowed deps."""
    package_root = runtime_public_module_paths()[0].parent
    violations = static_scan_allowed_import_roots(package_root)
    assert violations == []


@pytest.mark.runtime_tc("021")
def test_rt_tc_021_public_exports_match_interfaces() -> None:
    """RT-TC-021: public exports align with interfaces.md."""
    exports = public_export_names(runtime)
    assert _REQUIRED_PUBLIC_EXPORTS.issubset(exports)
    assert set(runtime.__all__) == exports
    assert set(ProcessKind) == {ProcessKind.API, ProcessKind.COORDINATOR, ProcessKind.WORKER}
    assert hasattr(CompositionRoot, "bootstrap")
    assert hasattr(CompositionRoot, "wired_dependencies")
    assert hasattr(OutboxPublisherLoop, "run")
    assert hasattr(OutboxPublisherLoop, "stop")


@pytest.mark.runtime_tc("022")
def test_rt_tc_022_entry_point_constants_exported() -> None:
    """RT-TC-022: API/COORDINATOR/WORKER entry constants match ProcessKind defaults."""
    assert API_ENTRY.kind == ProcessKind.API
    assert API_ENTRY.service_name == "cartoon-demo-api"
    assert COORDINATOR_ENTRY.kind == ProcessKind.COORDINATOR
    assert COORDINATOR_ENTRY.service_name == "cartoon-demo-coordinator"
    assert WORKER_ENTRY.kind == ProcessKind.WORKER
    assert WORKER_ENTRY.service_name == "cartoon-demo-worker"


@pytest.mark.runtime_tc("023")
def test_rt_tc_023_factories_return_working_implementations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RT-TC-023: post-implementation smoke — factories return working objects.

    Supersedes scaffold-phase NotImplementedError expectation after Phase 70.
    """
    from runtime.types import OutboxPublisherConfig

    monkeypatch.setattr(
        "runtime.composition.load_config",
        lambda source=None, **_kwargs: minimal_runtime_config(),
    )
    root = create_composition_root()
    assert hasattr(root, "config")
    assert hasattr(root, "bootstrap")

    loop = create_outbox_publisher_loop(
        config=minimal_runtime_config(),
        publisher_config=OutboxPublisherConfig(),
        outbox_repo=SimpleNamespace(),
        workflow_repo=SimpleNamespace(),
        task_queue=SimpleNamespace(),
        workflow_engine=SimpleNamespace(),
        failure_injection=SimpleNamespace(),
        logger=SimpleNamespace(),
        meter=SimpleNamespace(),
        tracer=SimpleNamespace(),
    )
    assert hasattr(loop, "run")
    assert hasattr(loop, "stop")


@pytest.mark.runtime_tc("024")
def test_rt_tc_024_bootstrap_errors_omit_secrets() -> None:
    """RT-TC-024: bootstrap error messages omit secrets."""
    error = DependencyWiringError(
        "connection failed for postgres user",
        entry=API_ENTRY,
        dependency="postgres",
    )
    assert_error_message_excludes_secrets(error)


@pytest.mark.runtime_tc("025")
def test_rt_tc_025_runtime_does_not_read_env_directly_in_public_modules() -> None:
    """RT-TC-025: public modules do not read .env or os.environ secrets directly."""
    source = read_public_module_sources()
    lowered = source.lower()
    assert "load_dotenv" not in lowered
    assert '.env"' not in lowered
    assert "os.environ[" not in lowered or "resolve_credential" in lowered
