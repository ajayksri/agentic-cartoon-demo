"""DefaultCliApp orchestration and public CLI entry points."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from config import ConfigLoadError, ConfigValidationError, ConfigSource, load_config

from .async_runner import AsyncRunner
from .dispatch import HandlerDispatchState, InitiateBootstrapState
from .errors import CliConfigError, CliError, map_to_connection_error
from .errors_render import ErrorRenderer
from .parser import ArgumentParser
from .protocols import CliDependencies
from .telemetry import CliTelemetry
from .types import CliCommandContext, SubcommandId


class DefaultCliApp:
    """CLI application entry — parse argv, dispatch subcommand, return exit code."""

    def __init__(
        self,
        *,
        deps: CliDependencies,
        parser: ArgumentParser | None = None,
        error_renderer: ErrorRenderer | None = None,
        telemetry: CliTelemetry | None = None,
        api_client: object | None = None,
    ) -> None:
        """Construct DefaultCliApp.

        Optional ``api_client`` injects a test double (e.g. ``FakeApiClient``) in place
        of ``create_api_client`` for contract tests per LLD §14. Production callers
        omit it and rely on parsed client config.
        """
        self._deps = deps
        self._parser = parser
        self._error_renderer = error_renderer or ErrorRenderer()
        self._telemetry_override = telemetry
        self._api_client_override = api_client

    def run(self, argv: Sequence[str] | None = None) -> int:
        parsed = None
        api_client = None
        try:
            parser = self._parser or ArgumentParser(registry=self._deps.registry)
            parsed = parser.parse(argv or sys.argv[1:])
            telemetry = self._telemetry_override or CliTelemetry(
                logger=self._deps.logger,
                tracer=self._deps.tracer,
            )
            api_client = self._resolve_api_client(parsed.client_config)
            initiate_bootstrap = self._maybe_bootstrap(parsed)
            ctx = CliCommandContext(
                subcommand_id=parsed.subcommand_id,
                workflow_id=parsed.workflow_id,
                api_client=api_client,
                logger=self._deps.logger,
                config_override=parsed.config_override,
                raw_args=parsed.raw_args,
            )
            dispatch = HandlerDispatchState(
                parsed=parsed,
                initiate_bootstrap=initiate_bootstrap,
            )
            handler = self._deps.registry.get_handler(parsed.subcommand_id)
            handler.bind_dispatch(dispatch)
            with telemetry.subcommand_scope(parsed.subcommand_id):
                result = handler.run(ctx=ctx)
            return int(result.exit_code)
        except CliError as err:
            if parsed is not None:
                telemetry = self._telemetry_override or CliTelemetry(
                    logger=self._deps.logger,
                    tracer=self._deps.tracer,
                )
                self._error_renderer.render(err, errout=sys.stderr)
                telemetry.emit_command_failed(parsed.subcommand_id, err)
            else:
                self._error_renderer.render(err, errout=sys.stderr)
            return int(err.exit_code)
        except Exception as exc:
            mapped = map_to_connection_error(exc)
            if parsed is not None:
                telemetry = self._telemetry_override or CliTelemetry(
                    logger=self._deps.logger,
                    tracer=self._deps.tracer,
                )
                self._error_renderer.render(mapped, errout=sys.stderr)
                telemetry.emit_command_failed(parsed.subcommand_id, mapped)
            else:
                self._error_renderer.render(mapped, errout=sys.stderr)
            return int(mapped.exit_code)
        finally:
            if api_client is not None:
                AsyncRunner().run(api_client.close())

    def _resolve_api_client(self, client_config):
        if self._api_client_override is not None:
            return self._api_client_override
        from .client import create_api_client

        return create_api_client(config=client_config, logger=self._deps.logger)

    def _maybe_bootstrap(self, parsed) -> InitiateBootstrapState | None:
        if parsed.subcommand_id != SubcommandId.INITIATE:
            return None
        config_path = parsed.client_config.config_path
        if config_path is None:
            return None
        try:
            base = load_config(ConfigSource(path=config_path))
            from .config_override import merge_cli_config_override

            effective = merge_cli_config_override(base, parsed.config_override)
        except (ConfigLoadError, ConfigValidationError) as exc:
            raise CliConfigError(str(exc)) from exc
        return InitiateBootstrapState(
            effective_config=effective,
            config_source_path=Path(config_path),
        )


def create_cli_app(
    *,
    deps: CliDependencies,
    api_client: object | None = None,
    telemetry: CliTelemetry | None = None,
) -> DefaultCliApp:
    """Default CliApp factory.

    Optional ``api_client`` and ``telemetry`` support contract-test injection (LLD §14).
    """
    return DefaultCliApp(deps=deps, api_client=api_client, telemetry=telemetry)


def run_cli(argv: Sequence[str] | None = None, *, deps: CliDependencies) -> int:
    """Primary public entry point for CLI process main()."""
    return create_cli_app(deps=deps).run(argv)
