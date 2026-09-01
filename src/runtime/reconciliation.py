"""Coordinator reconciliation loop (LLD §12, ADR-007)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Reconciliation scanner — periodic repair of stuck
# workflows when outbox publish, queue ACK, or worker lease boundaries fail partially.

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from config.types import AppConfig

from .telemetry import RuntimeTelemetry
from .types import CoordinatorLoopConfig

if TYPE_CHECKING:
    from workflow.protocols import WorkflowEngine


class ReconciliationScheduler:
    """Periodic reconcile_stuck_workflows invocations for the coordinator process."""

    def __init__(
        self,
        *,
        config: AppConfig,
        workflow_engine: WorkflowEngine,
        loop_config: CoordinatorLoopConfig,
        telemetry: RuntimeTelemetry,
        shutdown: threading.Event,
    ) -> None:
        self._config = config
        self._workflow_engine = workflow_engine
        self._loop_config = loop_config
        self._telemetry = telemetry
        self._shutdown = shutdown
        self._stopped = False

    def run(self) -> None:
        while not self._shutdown.is_set():
            self._reconcile_once()
            self._sleep_interruptible(self._loop_config.reconciliation_interval_seconds)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._shutdown.set()

    def _reconcile_once(self) -> None:
        result = self._workflow_engine.reconcile_stuck_workflows(
            config=self._config,
            batch_size=self._loop_config.reconciliation_batch_size,
        )
        self._telemetry.emit_reconciliation(result.scanned_count, result.repaired_count)

    def _sleep_interruptible(self, seconds: float) -> None:
        self._shutdown.wait(timeout=seconds)
