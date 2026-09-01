"""CLI command telemetry — logging, spans, and metrics."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from observability.protocols import Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor

from .constants import (
    EXIT_CLASS_CONNECTION,
    EXIT_CLASS_ERROR,
    EXIT_CLASS_SUCCESS,
    EXIT_CLASS_USAGE,
    METRIC_COMMAND_DURATION,
    METRIC_COMMANDS_TOTAL,
    SPAN_APPROVE,
    SPAN_HISTORY,
    SPAN_INITIATE,
    SPAN_OUTPUT,
    SPAN_STATUS,
    SPAN_TIMELINE,
)
from .errors import CliError
from .types import CliExitCode, SubcommandId

_SPAN_NAMES: dict[SubcommandId, str] = {
    SubcommandId.INITIATE: SPAN_INITIATE,
    SubcommandId.STATUS: SPAN_STATUS,
    SubcommandId.HISTORY: SPAN_HISTORY,
    SubcommandId.OUTPUT: SPAN_OUTPUT,
    SubcommandId.TIMELINE: SPAN_TIMELINE,
    SubcommandId.APPROVE: SPAN_APPROVE,
}

_COMMANDS_COUNTER_DESCRIPTOR = MetricDescriptor(
    logical_name=METRIC_COMMANDS_TOTAL,
    metric_type="counter",
    description="Total CLI commands by subcommand and exit class",
    allowed_label_keys=frozenset({"subcommand_id", "exit_code_class"}),
    unit="1",
)
_DURATION_HISTOGRAM_DESCRIPTOR = MetricDescriptor(
    logical_name=METRIC_COMMAND_DURATION,
    metric_type="histogram",
    description="CLI command duration by subcommand and exit class",
    allowed_label_keys=frozenset({"subcommand_id", "exit_code_class"}),
    unit="s",
)


@dataclass
class CapturedCliLogEvent:
    event: str
    level: str
    fields: dict[str, object]


class _NullSpan:
    """Minimal span used when no tracer is configured."""

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        del key, value

    def add_event(
        self,
        name: str,
        *,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        del name, attributes

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        del error_class, retryable

    def end(self, status: str = "OK") -> None:
        del status

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None


class CliTelemetry:
    """Structured telemetry for CLI subcommand execution."""

    def __init__(
        self,
        *,
        logger: Logger,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self._logger = logger
        self._tracer = tracer
        self._meter = meter
        self._commands_counter = None
        self._duration_histogram = None

    @contextmanager
    def subcommand_scope(self, subcommand_id: SubcommandId) -> Iterator[None]:
        started = time.monotonic()
        exit_code = CliExitCode.SUCCESS
        try:
            yield
        except CliError as err:
            exit_code = err.exit_code
            raise
        except Exception:
            exit_code = CliExitCode.CONNECTION
            raise
        finally:
            duration = time.monotonic() - started
            self.record_command_metric(
                subcommand_id=subcommand_id,
                exit_code=exit_code,
                duration_seconds=duration,
            )

    def emit_command_started(self, subcommand_id: SubcommandId) -> None:
        self._logger.info(
            "cli_command_started",
            f"CLI subcommand {subcommand_id.value} started",
            subcommand_id=subcommand_id.value,
        )

    def emit_command_completed(
        self,
        subcommand_id: SubcommandId,
        *,
        exit_code: int,
    ) -> None:
        self._logger.info(
            "cli_command_completed",
            f"CLI subcommand {subcommand_id.value} completed",
            subcommand_id=subcommand_id.value,
            exit_code=exit_code,
        )
        self._increment_commands_total(subcommand_id, CliExitCode(exit_code))

    def emit_command_failed(self, subcommand_id: SubcommandId, error: CliError) -> None:
        self._logger.error(
            "cli_command_failed",
            f"CLI subcommand {subcommand_id.value} failed",
            error_class=error.code,
            retryable=False,
            subcommand_id=subcommand_id.value,
            exit_code=int(error.exit_code),
        )
        self._increment_commands_total(subcommand_id, error.exit_code)

    def start_subcommand_span(self, subcommand_id: SubcommandId, **attrs: str) -> Span:
        span_name = _SPAN_NAMES[subcommand_id]
        if self._tracer is None:
            return _NullSpan()
        return self._tracer.start_span(span_name, attributes=attrs or None)

    def record_command_metric(
        self,
        *,
        subcommand_id: SubcommandId,
        exit_code: CliExitCode,
        duration_seconds: float,
    ) -> None:
        if self._meter is None:
            return
        labels = {
            "subcommand_id": subcommand_id.value,
            "exit_code_class": _exit_class_label(exit_code),
        }
        self._ensure_metrics()
        assert self._duration_histogram is not None
        self._duration_histogram.record(duration_seconds, labels=labels)

    def _increment_commands_total(
        self,
        subcommand_id: SubcommandId,
        exit_code: CliExitCode,
    ) -> None:
        if self._meter is None:
            return
        self._ensure_metrics()
        assert self._commands_counter is not None
        self._commands_counter.add(
            labels={
                "subcommand_id": subcommand_id.value,
                "exit_code_class": _exit_class_label(exit_code),
            }
        )

    def _ensure_metrics(self) -> None:
        if self._meter is None:
            return
        if self._commands_counter is None:
            self._commands_counter = self._meter.register_counter(
                _COMMANDS_COUNTER_DESCRIPTOR
            )
        if self._duration_histogram is None:
            self._duration_histogram = self._meter.register_histogram(
                _DURATION_HISTOGRAM_DESCRIPTOR
            )


class RecordingCliTelemetry(CliTelemetry):
    """Test seam capturing telemetry events."""

    def __init__(self) -> None:
        from cli.fakes.logger import RecordingLogger

        super().__init__(logger=RecordingLogger())
        self.log_events: list[CapturedCliLogEvent] = []
        self.span_names: list[str] = []
        self.metrics: list[tuple[str, dict[str, str], float]] = []
        self._event_names: list[str] = []

    @property
    def event_names(self) -> list[str]:
        return list(self._event_names)

    def clear(self) -> None:
        self.log_events.clear()
        self.span_names.clear()
        self.metrics.clear()
        self._event_names.clear()

    def emit_command_started(self, subcommand_id: SubcommandId) -> None:
        self._event_names.append("cli_command_started")
        super().emit_command_started(subcommand_id)

    def emit_command_completed(
        self,
        subcommand_id: SubcommandId,
        *,
        exit_code: int,
    ) -> None:
        self._event_names.append("cli_command_completed")
        super().emit_command_completed(subcommand_id, exit_code=exit_code)

    def emit_command_failed(self, subcommand_id: SubcommandId, error: CliError) -> None:
        self._event_names.append("cli_command_failed")
        super().emit_command_failed(subcommand_id, error)

    def record_command_metric(
        self,
        *,
        subcommand_id: SubcommandId,
        exit_code: CliExitCode,
        duration_seconds: float,
    ) -> None:
        labels = {
            "subcommand_id": subcommand_id.value,
            "exit_code_class": _exit_class_label(exit_code),
        }
        self.metrics.append((METRIC_COMMAND_DURATION, labels, duration_seconds))


def _exit_class_label(exit_code: CliExitCode) -> str:
    if exit_code == CliExitCode.SUCCESS:
        return EXIT_CLASS_SUCCESS
    if exit_code == CliExitCode.USAGE:
        return EXIT_CLASS_USAGE
    if exit_code == CliExitCode.CONNECTION:
        return EXIT_CLASS_CONNECTION
    return EXIT_CLASS_ERROR
