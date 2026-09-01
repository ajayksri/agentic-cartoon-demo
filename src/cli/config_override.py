"""Failure-injection flag parsing and config override merge (OPEN-009)."""

from __future__ import annotations

from collections.abc import Sequence

from config.types import AppConfig, FailureInjectionConfig, InjectionId

from .config_override_merger import ConfigOverrideMerger
from .config_override_merger import _default_merger as _merger
from .errors import CliUsageError
from .types import CliConfigOverride, CliFailureInjectionOverride


def parse_failure_injection_flags(argv: Sequence[str]) -> CliFailureInjectionOverride | None:
    """Extract failure-injection override from argv fragment (CG-CLI-002)."""
    from .parser import FailureInjectionFlagParser

    return FailureInjectionFlagParser().parse_failure_injection_flags(argv)


def _validate_injection_ids(injection_ids: frozenset[str]) -> frozenset[InjectionId]:
    """Reject unknown injection id strings before config merge."""
    validated: set[InjectionId] = set()
    for raw_id in injection_ids:
        try:
            validated.add(InjectionId(raw_id))
        except ValueError as exc:
            raise CliUsageError(
                f"Unknown failure injection id: {raw_id}",
            ) from exc
    return frozenset(validated)


def merge_failure_injection_override(
    base: FailureInjectionConfig,
    override: CliFailureInjectionOverride | None,
) -> FailureInjectionConfig:
    """Pure merge of CLI override into base failure_injection domain."""
    return _merger.merge_failure_injection_override(base, override)


def merge_cli_config_override(
    base: AppConfig,
    override: CliConfigOverride | None,
) -> AppConfig:
    """Apply CLI overrides to base config; returns effective config view (CG-CLI-008)."""
    return _merger.merge_cli_config_override(base, override)


def set_config_override_merger(merger: ConfigOverrideMerger) -> None:
    """Replace default merger for tests."""
    from . import config_override_merger as merger_module

    merger_module._default_merger = merger
