"""CLI module public surface."""

from __future__ import annotations

from .config_override import (
    merge_cli_config_override,
    merge_failure_injection_override,
    parse_failure_injection_flags,
)
from .errors import (
    CliApiError,
    CliConfigError,
    CliConnectionError,
    CliError,
    CliUsageError,
    map_api_error_envelope,
)
from .protocols import (
    ApiClient,
    CliApp,
    CliDependencies,
    build_default_subcommand_registry,
    create_api_client,
    create_cli_app,
    run_cli,
)
from .types import (
    CliClientConfig,
    CliCommandContext,
    CliCommandResult,
    CliConfigOverride,
    CliExitCode,
    CliFailureInjectionOverride,
    SubcommandHandler,
    SubcommandId,
    SubcommandRegistry,
    SubcommandSpec,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "ApiClient",
    "CliApiError",
    "CliApp",
    "CliClientConfig",
    "CliCommandContext",
    "CliCommandResult",
    "CliConfigError",
    "CliConfigOverride",
    "CliConnectionError",
    "CliDependencies",
    "CliError",
    "CliExitCode",
    "CliFailureInjectionOverride",
    "CliUsageError",
    "SubcommandHandler",
    "SubcommandId",
    "SubcommandRegistry",
    "SubcommandSpec",
    "build_default_subcommand_registry",
    "create_api_client",
    "create_cli_app",
    "map_api_error_envelope",
    "merge_cli_config_override",
    "merge_failure_injection_override",
    "parse_failure_injection_flags",
    "run_cli",
]
