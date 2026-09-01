"""Unit tests for CliTelemetry."""

from __future__ import annotations

import pytest

from cli.constants import EXIT_CLASS_USAGE, METRIC_COMMAND_DURATION
from cli.errors import CliUsageError
from cli.telemetry import CliTelemetry, RecordingCliTelemetry
from cli.types import CliExitCode, SubcommandId


def test_subcommand_scope_records_error_exit_class_on_failure() -> None:
    telemetry = RecordingCliTelemetry()

    with pytest.raises(CliUsageError):
        with telemetry.subcommand_scope(SubcommandId.STATUS):
            raise CliUsageError("failed")

    assert telemetry.metrics
    metric_name, labels, _duration = telemetry.metrics[-1]
    assert metric_name == METRIC_COMMAND_DURATION
    assert labels["exit_code_class"] == EXIT_CLASS_USAGE
    assert labels["subcommand_id"] == SubcommandId.STATUS.value


def test_subcommand_scope_records_success_exit_class() -> None:
    telemetry = RecordingCliTelemetry()

    with telemetry.subcommand_scope(SubcommandId.STATUS):
        pass

    _metric_name, labels, _duration = telemetry.metrics[-1]
    assert labels["exit_code_class"] == "success"


def test_emit_command_failed_records_event() -> None:
    telemetry = RecordingCliTelemetry()
    err = CliUsageError("bad")

    telemetry.emit_command_failed(SubcommandId.STATUS, err)

    assert telemetry.event_names.count("cli_command_failed") == 1
