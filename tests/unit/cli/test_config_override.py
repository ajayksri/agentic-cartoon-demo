"""Unit tests for config override merge."""

from __future__ import annotations

import pytest

from config.types import FailureInjectionConfig, InjectionId
from cli.config_override import merge_cli_config_override, merge_failure_injection_override
from cli.errors import CliUsageError
from cli.types import CliConfigOverride, CliFailureInjectionOverride


def test_merge_preserves_base_when_override_none() -> None:
    base = FailureInjectionConfig(enabled=False, active_injections=frozenset())
    assert merge_failure_injection_override(base, None) == base


def test_merge_enabled_false_is_noop() -> None:
    base = FailureInjectionConfig(
        enabled=True,
        active_injections=frozenset({InjectionId.FINJ_WKR_PRE}),
    )
    override = CliFailureInjectionOverride(enabled=False, active_injections=frozenset())
    assert merge_failure_injection_override(base, override) == base


def test_merge_activates_injection() -> None:
    base = FailureInjectionConfig(enabled=False, active_injections=frozenset())
    override = CliFailureInjectionOverride(
        enabled=True,
        active_injections=frozenset({"FINJ-WKR-PRE"}),
    )
    merged = merge_failure_injection_override(base, override)
    assert merged.enabled is True
    assert InjectionId.FINJ_WKR_PRE in merged.active_injections


def test_merge_unknown_injection_raises() -> None:
    base = FailureInjectionConfig(enabled=False, active_injections=frozenset())
    override = CliFailureInjectionOverride(
        enabled=True,
        active_injections=frozenset({"FINJ-UNKNOWN"}),
    )
    with pytest.raises(CliUsageError):
        merge_failure_injection_override(base, override)


def test_merge_enabled_true_requires_known_ids() -> None:
    base = FailureInjectionConfig(enabled=False, active_injections=frozenset())
    override = CliFailureInjectionOverride(enabled=True, active_injections=frozenset())
    with pytest.raises(CliUsageError):
        merge_failure_injection_override(base, override)


def test_merge_cli_config_override_preserves_factory_app_config() -> None:
    from tests.contract.worker.helpers import minimal_worker_config

    base = minimal_worker_config()
    override = CliConfigOverride(
        failure_injection=CliFailureInjectionOverride(
            enabled=True,
            active_injections=frozenset({"FINJ-WKR-PRE"}),
        )
    )
    merged = merge_cli_config_override(base, override)
    assert merged.is_injection_active(InjectionId.FINJ_WKR_PRE) is True
    assert merged.failure_injection.enabled is True
