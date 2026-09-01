"""Unit tests for RT-017 — process runners (LLD §14, §17)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config.types import TaskType
from runtime import COORDINATOR_ENTRY, WORKER_ENTRY, ProcessKind
from runtime.constants import (
    SCRIPT_API,
    SCRIPT_COORDINATOR,
    SCRIPT_WORKER,
)
from runtime.fakes.worker_loop import FakeWorkerLoop
from runtime.fakes.persistence import build_fake_persistence_bundle
from runtime.fakes.task_queue import FakeConnectionManager
from runtime.telemetry import RecordingRuntimeTelemetry
from runtime.types import WiredDependencies
from tests.unit.runtime.helpers import minimal_runtime_config


def test_run_worker_shutdown_sequence_stops_before_teardown() -> None:
    """RT-TC-017: WorkerLoop.stop() runs before connection teardown."""
    from runtime.runners import run_worker_shutdown_sequence

    order: list[str] = []
    worker_loop = FakeWorkerLoop()

    def _teardown() -> None:
        order.append("teardown")

    original_stop = worker_loop.stop

    def _stop() -> None:
        order.append("stop")
        original_stop()

    worker_loop.stop = _stop  # type: ignore[method-assign]

    run_worker_shutdown_sequence(worker_loop=worker_loop, teardown=_teardown)

    assert order == ["stop", "teardown"]
    assert worker_loop.stop_calls == 1


def test_run_worker_process_stops_loop_before_connection_close() -> None:
    """RT-TC-017: worker runner stops loop before redis/persistence teardown."""
    from runtime.bootstrap import BootstrapContext
    from runtime.composition import DefaultCompositionRoot
    from runtime.runners import run_worker_process

    config = minimal_runtime_config()
    worker_loop = FakeWorkerLoop()
    bundle = build_fake_persistence_bundle()
    redis = FakeConnectionManager()
    order: list[str] = []

    ctx = BootstrapContext(
        entry=WORKER_ENTRY,
        config=config,
        bundle=bundle,
        task_queue=MagicMock(),
        redis_connection_manager=redis,  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.WORKER),
        wired=WiredDependencies(
            entry=WORKER_ENTRY,
            config=config,
            worker_loop=worker_loop,
        ),
    )

    root = DefaultCompositionRoot(config)
    root._context = ctx  # noqa: SLF001

    original_run = FakeWorkerLoop.run

    def _run_loop(self: FakeWorkerLoop) -> None:
        order.append("run_started")
        original_run(self)
        order.append("run_finished")

    worker_loop.run = _run_loop.__get__(worker_loop, FakeWorkerLoop)  # type: ignore[method-assign]

    original_stop = worker_loop.stop

    def _stop() -> None:
        order.append("stop")
        original_stop()

    worker_loop.stop = _stop  # type: ignore[method-assign]

    original_redis_close = redis.close

    def _redis_close() -> None:
        order.append("redis_close")
        original_redis_close()

    redis.close = _redis_close  # type: ignore[method-assign]

    shutdown_requested = threading.Event()

    def _register(
        entry: object,
        *,
        grace_seconds: float,
        signal_registrar: object | None = None,
    ) -> SimpleNamespace:
        del entry, grace_seconds, signal_registrar
        shutdown_requested.set()
        return SimpleNamespace(requested=shutdown_requested)

    with patch("runtime.runners.create_composition_root", return_value=root):
        with patch.object(root, "bootstrap", return_value=MagicMock()):
            with patch("runtime.runners.ShutdownCoordinator.register", side_effect=_register):
                with patch("runtime.runners.ShutdownCoordinator.wait_for_signal"):
                    run_worker_process(worker_role=TaskType.COLLECT)

    assert "stop" in order
    assert "redis_close" in order
    assert order.index("stop") < order.index("redis_close")


def test_run_coordinator_process_starts_publisher_and_reconciliation_threads() -> None:
    """Coordinator runner starts outbox publisher and reconciliation threads."""
    from runtime.bootstrap import BootstrapContext
    from runtime.composition import DefaultCompositionRoot
    from runtime.runners import run_coordinator_process

    config = minimal_runtime_config()
    publisher = MagicMock()
    reconciler = MagicMock()
    started: list[str] = []

    def _publisher_run() -> None:
        started.append("publisher")

    def _reconciler_run() -> None:
        started.append("reconciliation")

    publisher.run = _publisher_run
    reconciler.run = _reconciler_run

    ctx = BootstrapContext(
        entry=COORDINATOR_ENTRY,
        config=config,
        bundle=build_fake_persistence_bundle(),
        task_queue=MagicMock(),
        redis_connection_manager=FakeConnectionManager(),  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.COORDINATOR),
        wired=WiredDependencies(
            entry=COORDINATOR_ENTRY,
            config=config,
            outbox_publisher=publisher,
        ),
        reconciliation_scheduler=reconciler,
        coordinator_shutdown=threading.Event(),
    )

    root = DefaultCompositionRoot(config)
    root._context = ctx  # noqa: SLF001
    shutdown_requested = threading.Event()

    def _register(
        entry: object,
        *,
        grace_seconds: float,
        signal_registrar: object | None = None,
    ) -> SimpleNamespace:
        del entry, grace_seconds, signal_registrar
        shutdown_requested.set()
        return SimpleNamespace(requested=shutdown_requested)

    with patch("runtime.runners.create_composition_root", return_value=root):
        with patch.object(root, "bootstrap", return_value=MagicMock()):
            with patch("runtime.runners.ShutdownCoordinator.register", side_effect=_register):
                with patch("runtime.runners.ShutdownCoordinator.wait_for_signal"):
                    run_coordinator_process()

    publisher.stop.assert_called_once()
    reconciler.stop.assert_called_once()
    assert "publisher" in started
    assert "reconciliation" in started


def test_parse_worker_role_from_argv_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployment role parsing maps --role and CARTOON_DEMO_WORKER_ROLE to TaskType."""
    from runtime.runners import _parse_worker_role_from_argv_or_env

    monkeypatch.setattr("runtime.runners.sys.argv", ["cartoon-demo-worker", "--role", "SELECT_TOPIC"])
    assert _parse_worker_role_from_argv_or_env() == TaskType.SELECT_TOPIC

    monkeypatch.setattr("runtime.runners.sys.argv", ["cartoon-demo-worker"])
    monkeypatch.setenv("CARTOON_DEMO_WORKER_ROLE", "REVIEW_SCENARIO")
    assert _parse_worker_role_from_argv_or_env() == TaskType.REVIEW_SCENARIO


def test_pyproject_scripts_point_to_runner_entries() -> None:
    """CG-RT-011: console scripts target runtime.runners entry functions."""
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    contents = pyproject.read_text(encoding="utf-8")

    assert f'{SCRIPT_API} = "runtime.runners:_entry_api"' in contents
    assert f'{SCRIPT_COORDINATOR} = "runtime.runners:_entry_coordinator"' in contents
    assert f'{SCRIPT_WORKER} = "runtime.runners:_entry_worker"' in contents


def test_run_api_process_uses_injectable_http_server() -> None:
    """API runner delegates to ApiHttpServer.serve with wired router."""
    from runtime.bootstrap import BootstrapContext
    from runtime.composition import DefaultCompositionRoot
    from runtime.runners import run_api_process
    from runtime.types import API_ENTRY

    config = minimal_runtime_config()
    router = MagicMock()
    ctx = BootstrapContext(
        entry=API_ENTRY,
        config=config,
        bundle=build_fake_persistence_bundle(),
        task_queue=MagicMock(),
        redis_connection_manager=FakeConnectionManager(),  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.API),
        wired=WiredDependencies(entry=API_ENTRY, config=config, api_router=router),
    )
    root = DefaultCompositionRoot(config)
    root._context = ctx  # noqa: SLF001

    http_server = MagicMock()

    with patch("runtime.runners.create_composition_root", return_value=root):
        with patch.object(root, "bootstrap", return_value=MagicMock()):
            run_api_process(http_server=http_server)

    http_server.serve.assert_called_once()
    assert http_server.serve.call_args.kwargs["router"] is router


def test_run_worker_process_teardown_on_grace_timeout() -> None:
    """RT-017-R001: connection teardown runs even when shutdown grace is exceeded."""
    from runtime.bootstrap import BootstrapContext
    from runtime.composition import DefaultCompositionRoot
    from runtime.errors import ProcessShutdownError
    from runtime.runners import run_worker_process

    config = minimal_runtime_config()
    worker_loop = FakeWorkerLoop()
    bundle = build_fake_persistence_bundle()
    redis = FakeConnectionManager()
    close_calls: list[str] = []

    ctx = BootstrapContext(
        entry=WORKER_ENTRY,
        config=config,
        bundle=bundle,
        task_queue=MagicMock(),
        redis_connection_manager=redis,  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.WORKER),
        wired=WiredDependencies(
            entry=WORKER_ENTRY,
            config=config,
            worker_loop=worker_loop,
        ),
    )

    root = DefaultCompositionRoot(config)
    root._context = ctx  # noqa: SLF001

    original_redis_close = redis.close

    def _redis_close() -> None:
        close_calls.append("redis")
        original_redis_close()

    redis.close = _redis_close  # type: ignore[method-assign]

    shutdown_requested = threading.Event()

    def _register(
        entry: object,
        *,
        grace_seconds: float,
        signal_registrar: object | None = None,
    ) -> SimpleNamespace:
        del entry, grace_seconds, signal_registrar
        shutdown_requested.set()
        return SimpleNamespace(requested=shutdown_requested)

    def _join_with_grace(*_args: object, **_kwargs: object) -> None:
        raise ProcessShutdownError("grace exceeded", entry=WORKER_ENTRY)

    with patch("runtime.runners.create_composition_root", return_value=root):
        with patch.object(root, "bootstrap", return_value=MagicMock()):
            with patch("runtime.runners.ShutdownCoordinator.register", side_effect=_register):
                with patch("runtime.runners.ShutdownCoordinator.wait_for_signal"):
                    with patch(
                        "runtime.runners.ShutdownCoordinator.join_with_grace",
                        side_effect=_join_with_grace,
                    ):
                        with pytest.raises(ProcessShutdownError):
                            run_worker_process(worker_role=TaskType.COLLECT)

    assert "redis" in close_calls
