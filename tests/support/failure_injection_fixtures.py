"""Shared failure_injection test fixtures (LLD §10.2)."""

from __future__ import annotations

from dataclasses import dataclass

from config.types import AppConfig, FailureInjectionConfig, InjectionId


@dataclass(frozen=True, slots=True)
class StubAppConfig:
    """Minimal AppConfig double for failure_injection registry tests."""

    failure_injection: FailureInjectionConfig

    def is_injection_active(self, injection_id: InjectionId) -> bool:
        if not self.failure_injection.enabled:
            return False
        return injection_id in self.failure_injection.active_injections


def stub_app_config(
    *,
    enabled: bool = False,
    active: frozenset[InjectionId] = frozenset(),
) -> StubAppConfig:
    """Return StubAppConfig with controlled activation predicate."""
    return StubAppConfig(
        failure_injection=FailureInjectionConfig(
            enabled=enabled,
            active_injections=active,
        ),
    )
