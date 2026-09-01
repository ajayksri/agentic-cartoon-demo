"""Base subcommand handler pipeline."""

from __future__ import annotations

from ..async_runner import AsyncRunner
from ..dispatch import HandlerDispatchState
from ..errors import CliError, map_to_connection_error
from ..render import OutputRenderer
from ..telemetry import CliTelemetry
from ..types import CliCommandContext, CliCommandResult, CliExitCode, SubcommandId
from ..validation import InputValidator


class BaseSubcommandHandler:
    """Common handler pipeline with telemetry and error mapping."""

    def __init__(
        self,
        *,
        subcommand_id: SubcommandId,
        validator: InputValidator,
        renderer: OutputRenderer,
        telemetry: CliTelemetry,
        async_runner: AsyncRunner | None = None,
    ) -> None:
        self._subcommand_id = subcommand_id
        self._validator = validator
        self._renderer = renderer
        self._telemetry = telemetry
        self._async_runner = async_runner or AsyncRunner()
        self._dispatch: HandlerDispatchState | None = None

    def bind_dispatch(self, state: HandlerDispatchState) -> None:
        self._dispatch = state

    def run(self, *, ctx: CliCommandContext) -> CliCommandResult:
        self._telemetry.emit_command_started(self._subcommand_id)
        span = self._telemetry.start_subcommand_span(self._subcommand_id)
        span_status = "OK"
        try:
            self._execute(ctx)
            self._telemetry.emit_command_completed(
                self._subcommand_id,
                exit_code=int(CliExitCode.SUCCESS),
            )
            return CliCommandResult(exit_code=CliExitCode.SUCCESS)
        except CliError as err:
            span.record_exception(err.code, retryable=False)
            span_status = "ERROR"
            raise
        except Exception as exc:
            mapped = map_to_connection_error(exc)
            span.record_exception(mapped.code, retryable=False)
            span_status = "ERROR"
            raise mapped from exc
        finally:
            span.end(status=span_status)

    def _execute(self, ctx: CliCommandContext) -> None:
        raise NotImplementedError
