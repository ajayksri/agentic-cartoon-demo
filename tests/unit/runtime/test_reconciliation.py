"""Unit tests for RT-008 — ReconciliationScheduler (LLD §12)."""

from __future__ import annotations

import threading
import time

from workflow.types import ReconciliationResult

from runtime.reconciliation import ReconciliationScheduler
from runtime.types import CoordinatorLoopConfig
from tests.unit.runtime.helpers import minimal_runtime_config


def test_reconcile_once_records_engine_call_with_batch_size() -> None:
    engine = _FakeWorkflowEngine()
    telemetry = _NoOpTelemetry()
    loop_config = CoordinatorLoopConfig(reconciliation_batch_size=42)
    scheduler = ReconciliationScheduler(
        config=minimal_runtime_config(),
        workflow_engine=engine,
        loop_config=loop_config,
        telemetry=telemetry,
        shutdown=threading.Event(),
    )

    scheduler._reconcile_once()  # type: ignore[attr-defined]

    assert len(engine.reconcile_calls) == 1
    assert engine.reconcile_calls[0]["batch_size"] == 42


def test_stop_is_idempotent_and_prevents_further_cycles() -> None:
    engine = _FakeWorkflowEngine()
    shutdown = threading.Event()
    scheduler = ReconciliationScheduler(
        config=minimal_runtime_config(),
        workflow_engine=engine,
        loop_config=CoordinatorLoopConfig(reconciliation_interval_seconds=0.01),
        telemetry=_NoOpTelemetry(),
        shutdown=shutdown,
    )

    thread = threading.Thread(target=scheduler.run, daemon=True)
    thread.start()
    time.sleep(0.05)
    scheduler.stop()
    scheduler.stop()
    calls_after_stop = len(engine.reconcile_calls)
    time.sleep(0.05)
    thread.join(timeout=1.0)

    assert shutdown.is_set()
    assert len(engine.reconcile_calls) == calls_after_stop
    assert calls_after_stop >= 1


class _FakeWorkflowEngine:
    def __init__(self) -> None:
        self.reconcile_calls: list[dict[str, object]] = []

    def reconcile_stuck_workflows(
        self,
        *,
        config: object,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        self.reconcile_calls.append({"config": config, "batch_size": batch_size})
        return ReconciliationResult(scanned_count=3, repaired_count=1, reports=())


class _NoOpTelemetry:
    def emit_reconciliation(self, _scanned: int, _repaired: int) -> None:
        return None
