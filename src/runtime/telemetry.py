"""Runtime process telemetry — logs and metrics (LLD §15)."""

from __future__ import annotations

from dataclasses import dataclass, field

from observability.protocols import Logger, Meter
from observability.types import MetricDescriptor

from .constants import (
    METRIC_BOOTSTRAP_FAILURES,
    METRIC_OUTBOX_PUBLISHED,
    METRIC_OUTBOX_PUBLISH_FAILURES,
    METRIC_RECONCILIATION_REPAIRS,
)
from .types import OutboxPublishBatchResult, ProcessEntryPoint, ProcessKind


@dataclass
class RuntimeTelemetryEvents:
    """Captured runtime telemetry events for tests."""

    bootstrap_started: bool = False
    bootstrap_completed: bool = False
    outbox_batches: list[OutboxPublishBatchResult] = field(default_factory=list)
    reconciliation_cycles: list[tuple[int, int]] = field(default_factory=list)
    shutdown_started: bool = False
    shutdown_completed: bool = False


class RuntimeTelemetry:
    """Structured runtime logs and cardinality-safe metrics."""

    _ALLOWED_LABELS = frozenset({"process_kind"})

    def __init__(self, *, logger: Logger, meter: Meter, process_kind: ProcessKind) -> None:
        self._logger = logger
        self._meter = meter
        self._process_kind = process_kind
        self._bootstrap_failures: object | None = None
        self._outbox_published: object | None = None
        self._outbox_failures: object | None = None
        self._reconciliation_repairs: object | None = None

    @staticmethod
    def allowed_metric_labels() -> tuple[str, ...]:
        return ("process_kind",)

    def _labels(self) -> dict[str, str]:
        return {"process_kind": self._process_kind.value}

    def _ensure_counters(self) -> None:
        if self._bootstrap_failures is not None:
            return
        self._bootstrap_failures = self._meter.register_counter(
            MetricDescriptor(
                logical_name=METRIC_BOOTSTRAP_FAILURES,
                metric_type="counter",
                unit="1",
                description=METRIC_BOOTSTRAP_FAILURES,
                allowed_label_keys=self._ALLOWED_LABELS,
            )
        )
        self._outbox_published = self._meter.register_counter(
            MetricDescriptor(
                logical_name=METRIC_OUTBOX_PUBLISHED,
                metric_type="counter",
                unit="1",
                description=METRIC_OUTBOX_PUBLISHED,
                allowed_label_keys=self._ALLOWED_LABELS,
            )
        )
        self._outbox_failures = self._meter.register_counter(
            MetricDescriptor(
                logical_name=METRIC_OUTBOX_PUBLISH_FAILURES,
                metric_type="counter",
                unit="1",
                description=METRIC_OUTBOX_PUBLISH_FAILURES,
                allowed_label_keys=self._ALLOWED_LABELS,
            )
        )
        self._reconciliation_repairs = self._meter.register_counter(
            MetricDescriptor(
                logical_name=METRIC_RECONCILIATION_REPAIRS,
                metric_type="counter",
                unit="1",
                description=METRIC_RECONCILIATION_REPAIRS,
                allowed_label_keys=self._ALLOWED_LABELS,
            )
        )

    def log_process_started(self, *, kind: ProcessKind, service_name: str) -> None:
        self._logger.info(
            "process_started",
            "Process started",
            process_kind=kind.value,
            service_name=service_name,
        )

    def log_bootstrap_complete(self, *, kind: ProcessKind, service_name: str) -> None:
        self._logger.info(
            "bootstrap_complete",
            "Bootstrap complete",
            process_kind=kind.value,
            service_name=service_name,
        )

    def log_bootstrap_failed(self, *, kind: ProcessKind, error_class: str) -> None:
        self._logger.error(
            "bootstrap_failed",
            "Bootstrap failed",
            process_kind=kind.value,
            error_class=error_class,
        )

    def log_shutdown_started(self, *, kind: ProcessKind, service_name: str) -> None:
        self._logger.info(
            "shutdown_started",
            "Shutdown started",
            process_kind=kind.value,
            service_name=service_name,
        )

    def log_shutdown_complete(self, *, kind: ProcessKind, service_name: str) -> None:
        self._logger.info(
            "shutdown_complete",
            "Shutdown complete",
            process_kind=kind.value,
            service_name=service_name,
        )

    def emit_outbox_batch(self, result: OutboxPublishBatchResult) -> None:
        self._logger.info(
            "outbox_batch_published",
            "Outbox batch published",
            fetched_count=result.fetched_count,
            published_count=result.published_count,
            failed_count=result.failed_count,
            skipped_count=result.skipped_count,
        )
        self.record_outbox_published(result.published_count)

    def emit_reconciliation(self, scanned: int, repaired: int) -> None:
        self._logger.info(
            "reconciliation_cycle",
            "Reconciliation cycle complete",
            scanned=scanned,
            repaired=repaired,
        )
        self.record_reconciliation_repair(repaired)

    def record_bootstrap_failure(self) -> None:
        self._ensure_counters()
        self._bootstrap_failures.add(1.0, labels=self._labels())  # type: ignore[union-attr]

    def record_outbox_published(self, count: int) -> None:
        if count <= 0:
            return
        self._ensure_counters()
        self._outbox_published.add(float(count), labels=self._labels())  # type: ignore[union-attr]

    def record_outbox_publish_failure(self) -> None:
        self._ensure_counters()
        self._outbox_failures.add(1.0, labels=self._labels())  # type: ignore[union-attr]

    def record_reconciliation_repair(self, count: int) -> None:
        if count <= 0:
            return
        self._ensure_counters()
        self._reconciliation_repairs.add(float(count), labels=self._labels())  # type: ignore[union-attr]


class RecordingRuntimeTelemetry(RuntimeTelemetry):
    """Captures events and call-order indices for RT-TC-005."""

    def __init__(self, *, process_kind: ProcessKind) -> None:
        from types import SimpleNamespace

        from observability.fakes import create_fake_bindings

        config = SimpleNamespace(
            service_name="runtime-test",
            log_level="DEBUG",
            strict_telemetry_errors=True,
        )
        logger, meter, _tracer, _correlation = create_fake_bindings(config)
        super().__init__(logger=logger, meter=meter, process_kind=process_kind)
        self.events = RuntimeTelemetryEvents()
        self._call_index = 0
        self.configure_observability_index: int | None = None
        self.loop_start_index: int | None = None

    def record_configure_observability(self) -> None:
        self.configure_observability_index = self._call_index
        self._call_index += 1

    def record_loop_start(self) -> None:
        self.loop_start_index = self._call_index
        self._call_index += 1

    def emit_bootstrap_started(self, *, entry: ProcessEntryPoint) -> None:
        self.events.bootstrap_started = True
        self.log_process_started(kind=entry.kind, service_name=entry.service_name)

    def emit_bootstrap_completed(self, *, entry: ProcessEntryPoint) -> None:
        self.events.bootstrap_completed = True
        self.log_bootstrap_complete(kind=entry.kind, service_name=entry.service_name)
