"""Public CLI value and registry types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from observability.protocols import Logger

    from .protocols import ApiClient


class SubcommandId(StrEnum):
    """Stable subcommand identifiers for registry and tests."""

    INITIATE = "initiate"
    STATUS = "status"
    HISTORY = "history"
    OUTPUT = "output"
    TIMELINE = "timeline"
    APPROVE = "approve"


class CliExitCode(IntEnum):
    """Process exit codes for CLI commands."""

    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    CONNECTION = 3


@dataclass(frozen=True, slots=True)
class SubcommandSpec:
    """Immutable subcommand metadata registered with CliApp."""

    id: SubcommandId
    name: str
    description: str
    requires_workflow_id: bool = False


class SubcommandHandler(Protocol):
    """Executes one subcommand with parsed context."""

    def run(self, *, ctx: CliCommandContext) -> CliCommandResult:
        """Run subcommand logic; raise CliError on failure."""
        ...


@dataclass(frozen=True, slots=True)
class SubcommandRegistry:
    """Immutable map of subcommand id to spec and handler."""

    specs: Mapping[SubcommandId, SubcommandSpec]
    handlers: Mapping[SubcommandId, SubcommandHandler]

    def get_spec(self, subcommand_id: SubcommandId) -> SubcommandSpec:
        return self.specs[subcommand_id]

    def get_handler(self, subcommand_id: SubcommandId) -> SubcommandHandler:
        return self.handlers[subcommand_id]


@dataclass(frozen=True, slots=True)
class CliClientConfig:
    """Transport and bootstrap settings for the CLI process."""

    api_base_url: str
    config_path: Path | None = None
    request_timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CliFailureInjectionOverride:
    """CLI-selected failure injection state propagated into config (OPEN-009)."""

    enabled: bool
    active_injections: frozenset[str] = frozenset()
    """InjectionId string values; typed as str at boundary to avoid config re-export."""


@dataclass(frozen=True, slots=True)
class CliConfigOverride:
    """Aggregate CLI bootstrap overrides merged into AppConfig."""

    failure_injection: CliFailureInjectionOverride | None = None


@dataclass(frozen=True, slots=True)
class CliCommandContext:
    """Runtime context passed to subcommand handlers."""

    subcommand_id: SubcommandId
    workflow_id: str | None
    api_client: ApiClient
    logger: Logger
    config_override: CliConfigOverride | None = None
    raw_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CliCommandResult:
    """Structured outcome for CliApp exit-code mapping."""

    exit_code: CliExitCode
    message: str | None = None
    workflow_id: str | None = None
