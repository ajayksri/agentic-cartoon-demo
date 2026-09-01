"""Public protocol definitions for the failure_injection module contract boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import InjectionContext, InjectionId


@runtime_checkable
class Hook(Protocol):
    """Pluggable injection effect invoked when an injection ID is active."""

    def invoke(self, context: InjectionContext | None = None) -> None:
        """Execute the injection effect when the ID is active."""
        ...


@runtime_checkable
class FailureInjectionRegistry(Protocol):
    """Config-gated hook registry for deliberate failure simulation."""

    def register_hook(self, injection_id: InjectionId, hook: Hook) -> None:
        """Register a hook for an injection point; raises DuplicateHookError on duplicate."""
        ...

    def is_active(self, injection_id: InjectionId) -> bool:
        """Return whether the injection ID is active per application configuration."""
        ...

    def invoke_if_active(
        self,
        injection_id: InjectionId,
        *,
        context: InjectionContext | None = None,
    ) -> bool:
        """Invoke the registered hook when active; return True if invoked, False if inactive."""
        ...
