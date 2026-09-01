"""Unit tests for BaseSubcommandHandler pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from cli.app import DefaultCliApp
from cli.errors import CliUsageError
from cli.fakes.api_client import FakeApiClient
from cli.handlers.base import BaseSubcommandHandler
from cli.render import OutputRenderer
from cli.telemetry import CliTelemetry, RecordingCliTelemetry
from cli.protocols import CliDependencies
from cli.types import (
    CliClientConfig,
    CliCommandContext,
    CliExitCode,
    SubcommandId,
    SubcommandRegistry,
    SubcommandSpec,
)
from cli.validation import InputValidator


class _CapturingSpan:
    def __init__(self) -> None:
        self.ended = False
        self.status: str | None = None
        self.exceptions: list[tuple[str, bool]] = []

    def record_exception(self, error_class: str, *, retryable: bool) -> None:
        self.exceptions.append((error_class, retryable))

    def end(self, status: str = "OK") -> None:
        self.ended = True
        self.status = status


class _CapturingTelemetry(CliTelemetry):
    def __init__(self) -> None:
        from cli.fakes.logger import RecordingLogger

        super().__init__(logger=RecordingLogger())
        self.last_span: _CapturingSpan | None = None

    def start_subcommand_span(self, subcommand_id: SubcommandId, **attrs: str) -> Any:
        del subcommand_id, attrs
        self.last_span = _CapturingSpan()
        return self.last_span


class _SuccessHandler(BaseSubcommandHandler):
    def _execute(self, ctx: CliCommandContext) -> None:
        del ctx


class _FailHandler(BaseSubcommandHandler):
    def _execute(self, ctx: CliCommandContext) -> None:
        del ctx
        raise CliUsageError("handler failed")


def _handler(telemetry: CliTelemetry, handler_cls: type[BaseSubcommandHandler]) -> BaseSubcommandHandler:
    return handler_cls(
        subcommand_id=SubcommandId.STATUS,
        validator=InputValidator(),
        renderer=OutputRenderer(),
        telemetry=telemetry,
    )


def _ctx() -> CliCommandContext:
    from cli.fakes.logger import RecordingLogger

    return CliCommandContext(
        subcommand_id=SubcommandId.STATUS,
        workflow_id="wf-1",
        api_client=FakeApiClient(),
        logger=RecordingLogger(),
    )


def test_run_ends_span_once_on_success() -> None:
    telemetry = _CapturingTelemetry()
    handler = _handler(telemetry, _SuccessHandler)

    result = handler.run(ctx=_ctx())

    assert result.exit_code == CliExitCode.SUCCESS
    assert telemetry.last_span is not None
    assert telemetry.last_span.ended is True
    assert telemetry.last_span.status == "OK"


def test_run_ends_span_on_cli_error() -> None:
    telemetry = _CapturingTelemetry()
    handler = _handler(telemetry, _FailHandler)

    with pytest.raises(CliUsageError):
        handler.run(ctx=_ctx())

    assert telemetry.last_span is not None
    assert telemetry.last_span.ended is True
    assert telemetry.last_span.status == "ERROR"
    assert telemetry.last_span.exceptions == [("CLI_USAGE", False)]


def test_run_does_not_emit_command_failed() -> None:
    telemetry = RecordingCliTelemetry()
    handler = _handler(telemetry, _FailHandler)

    with pytest.raises(CliUsageError):
        handler.run(ctx=_ctx())

    assert telemetry.event_names.count("cli_command_failed") == 0


def test_app_emits_single_command_failed_on_handler_error() -> None:
    telemetry = RecordingCliTelemetry()
    fail_handler = _handler(telemetry, _FailHandler)
    deps = CliDependencies(
        client_config=CliClientConfig(api_base_url="http://test"),
        registry=SubcommandRegistry(
            specs={
                SubcommandId.STATUS: SubcommandSpec(
                    id=SubcommandId.STATUS,
                    name="status",
                    description="Status",
                    requires_workflow_id=True,
                ),
            },
            handlers={SubcommandId.STATUS: fail_handler},
        ),
        logger=telemetry._logger,  # type: ignore[attr-defined]
    )
    app = DefaultCliApp(deps=deps, telemetry=telemetry, api_client=FakeApiClient())

    exit_code = app.run(["status", "wf-1"])

    assert exit_code == CliExitCode.USAGE
    assert telemetry.event_names.count("cli_command_failed") == 1
