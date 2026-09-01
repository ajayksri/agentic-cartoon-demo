"""Unit tests for RT-002 — RuntimeTelemetry (LLD §15, §2.5)."""

from __future__ import annotations

from runtime import API_ENTRY, ProcessKind

_LLD_METRIC_BOOTSTRAP_FAILURES = "runtime_bootstrap_failures_total"
_LLD_METRIC_OUTBOX_PUBLISHED = "runtime_outbox_published_total"


def test_recording_telemetry_captures_configure_before_loop_index() -> None:
    """RT-TC-005 seam: configure_observability index precedes loop start index."""
    from runtime.telemetry import RecordingRuntimeTelemetry

    telemetry = RecordingRuntimeTelemetry(process_kind=ProcessKind.API)

    telemetry.record_configure_observability()
    telemetry.record_loop_start()

    assert telemetry.configure_observability_index == 0
    assert telemetry.loop_start_index == 1
    assert telemetry.configure_observability_index < telemetry.loop_start_index


def test_recording_telemetry_records_bootstrap_events() -> None:
    """LLD §15: bootstrap_started / bootstrap_completed flags captured."""
    from runtime.telemetry import RecordingRuntimeTelemetry

    telemetry = RecordingRuntimeTelemetry(process_kind=ProcessKind.COORDINATOR)
    telemetry.emit_bootstrap_started(entry=API_ENTRY)
    telemetry.emit_bootstrap_completed(entry=API_ENTRY)

    assert telemetry.events.bootstrap_started is True
    assert telemetry.events.bootstrap_completed is True


def test_metric_logical_names_match_constants() -> None:
    """LLD §3 / §15: metric logical names from constants module."""
    from runtime.constants import METRIC_BOOTSTRAP_FAILURES, METRIC_OUTBOX_PUBLISHED

    assert METRIC_BOOTSTRAP_FAILURES == _LLD_METRIC_BOOTSTRAP_FAILURES
    assert METRIC_OUTBOX_PUBLISHED == _LLD_METRIC_OUTBOX_PUBLISHED


def test_metric_labels_use_process_kind_only() -> None:
    """MOD-RT-INV-028: metrics labeled with process_kind only."""
    from runtime.telemetry import RuntimeTelemetry

    labels = RuntimeTelemetry.allowed_metric_labels()  # type: ignore[attr-defined]
    assert labels == ("process_kind",)


def test_no_efms_instrumentation_symbols() -> None:
    """MOD-RT-INV-008: telemetry module avoids EFMS-specific symbols."""
    import runtime.telemetry as telemetry_module

    source = open(telemetry_module.__file__, encoding="utf-8").read().lower()
    assert "efms" not in source
