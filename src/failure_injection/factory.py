"""Registry factory (internal construction path)."""

from __future__ import annotations

from collections.abc import Callable

from config.types import AppConfig, InjectionId

from .protocols import FailureInjectionRegistry
from .registry import DefaultFailureInjectionRegistry
from .types import InjectionContext


def create_failure_injection_registry(config: AppConfig) -> FailureInjectionRegistry:
    """Public factory; V1 production uses default wrap_hook_errors=False."""
    return build_failure_injection_registry(config)


def build_failure_injection_registry(
    config: AppConfig,
    *,
    wrap_hook_errors: bool = False,
    on_hook_invoked: Callable[[InjectionId, InjectionContext | None], None] | None = None,
) -> DefaultFailureInjectionRegistry:
    """Internal extended constructor with test-only kwargs."""
    return DefaultFailureInjectionRegistry(
        config,
        wrap_hook_errors=wrap_hook_errors,
        on_hook_invoked=on_hook_invoked,
    )
