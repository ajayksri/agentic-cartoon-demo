"""Unit tests for RT-013 — CoordinatorProcessWiring."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from runtime import COORDINATOR_ENTRY
from runtime.bootstrap import BootstrapContext
from runtime.fakes.persistence import build_fake_persistence_bundle
from runtime.fakes.task_queue import FakeConnectionManager
from runtime.reconciliation import ReconciliationScheduler
from runtime.telemetry import RecordingRuntimeTelemetry
from runtime.types import CoordinatorLoopConfig, ProcessKind, WiredDependencies
from runtime.wiring.coordinator import CoordinatorProcessWiring
from tests.unit.runtime.helpers import minimal_runtime_config


def test_coordinator_wiring_populates_outbox_queue_and_engine() -> None:
    ctx = _bootstrap_context()
    shutdown = threading.Event()

    wired = CoordinatorProcessWiring().wire(ctx, shutdown=shutdown)

    assert wired.wired.outbox_publisher is not None
    assert wired.wired.task_queue is not None
    assert wired.wired.workflow_engine is not None
    assert wired.wired.api_router is None
    assert wired.wired.worker_loop is None


def test_coordinator_wiring_constructs_reconciliation_scheduler() -> None:
    ctx = _bootstrap_context()
    loop_config = CoordinatorLoopConfig(reconciliation_batch_size=25)

    wired = CoordinatorProcessWiring().wire(ctx, loop_config=loop_config)

    assert isinstance(wired.reconciliation_scheduler, ReconciliationScheduler)
    assert wired.coordinator_shutdown is not None
    assert wired.reconciliation_scheduler._loop_config.reconciliation_batch_size == 25  # type: ignore[attr-defined]


def _bootstrap_context() -> BootstrapContext:
    config = minimal_runtime_config()
    return BootstrapContext(
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
        wired=WiredDependencies(entry=COORDINATOR_ENTRY, config=config),
    )
