"""Failure injection module public surface."""

from __future__ import annotations

from .factory import create_failure_injection_registry
from .protocols import FailureInjectionRegistry, Hook
from .types import (
    DuplicateHookError,
    FailureInjectionError,
    HookNotRegisteredError,
    InjectionContext,
    InjectionId,
    InjectionInvocationError,
    RegistryNotConfiguredError,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "DuplicateHookError",
    "FailureInjectionError",
    "FailureInjectionRegistry",
    "Hook",
    "HookNotRegisteredError",
    "InjectionContext",
    "InjectionId",
    "InjectionInvocationError",
    "RegistryNotConfiguredError",
    "configure_failure_injection",
    "create_failure_injection_registry",
    "get_failure_injection_registry",
]

_registry: FailureInjectionRegistry | None = None


def configure_failure_injection(registry: FailureInjectionRegistry) -> None:
    """Bind process-scoped registry (called by runtime composition root)."""
    global _registry
    _registry = registry


def get_failure_injection_registry() -> FailureInjectionRegistry:
    """Return bound registry; raises RegistryNotConfiguredError if unset."""
    if _registry is None:
        raise RegistryNotConfiguredError(
            "Failure injection registry not configured; "
            "call configure_failure_injection() first (FINJ-E001)."
        )
    return _registry


def _reset_failure_injection_state() -> None:
    """Clear process singleton; for unit tests only (test_singleton.py)."""
    global _registry
    _registry = None
