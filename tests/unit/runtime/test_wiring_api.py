"""Unit tests for RT-012 — ApiProcessWiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from runtime import API_ENTRY
from runtime.bootstrap import BootstrapContext
from runtime.fakes.persistence import build_fake_persistence_bundle
from runtime.fakes.task_queue import FakeConnectionManager
from runtime.telemetry import RecordingRuntimeTelemetry
from runtime.types import ProcessKind, WiredDependencies
from runtime.wiring.api import ApiProcessWiring
from tests.unit.runtime.helpers import minimal_runtime_config


def test_api_wiring_populates_router_and_null_worker_outbox_fields() -> None:
    ctx = _bootstrap_context()
    router = object()
    wired = ApiProcessWiring().wire(
        ctx,
        router_factory=lambda **_kwargs: router,
    )

    assert wired.wired.api_router is router
    assert wired.wired.worker_loop is None
    assert wired.wired.outbox_publisher is None
    assert wired.wired.workflow_engine is not None
    assert wired.wired.task_queue is not None


def test_api_wiring_builds_postgres_and_redis_probes() -> None:
    ctx = _bootstrap_context()
    captured: dict[str, object] = {}

    def _router_factory(*, deps: object, mutating_context: object) -> object:
        captured["deps"] = deps
        captured["mutating_context"] = mutating_context
        return object()

    ApiProcessWiring().wire(ctx, router_factory=_router_factory)

    deps = captured["deps"]
    assert len(deps.readiness_probes) == 2  # type: ignore[attr-defined]
    assert deps.service_name == API_ENTRY.service_name  # type: ignore[attr-defined]
    assert captured["mutating_context"] is not None


def _bootstrap_context() -> BootstrapContext:
    config = minimal_runtime_config()
    bundle = build_fake_persistence_bundle()
    return BootstrapContext(
        entry=API_ENTRY,
        config=config,
        bundle=bundle,
        task_queue=MagicMock(),
        redis_connection_manager=FakeConnectionManager(),  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.API),
        wired=WiredDependencies(entry=API_ENTRY, config=config),
    )
