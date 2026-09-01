"""DefaultFailureInjectionRegistry implementation (internal)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Failure injection at boundaries — deliberate crashes,
# duplicate delivery, and provider errors validate resilience without ad-hoc test patches.
# GUARDRAIL: Security — failure hooks are config-gated only; never exposed on public API.

from __future__ import annotations

import threading
from collections.abc import Callable

from config.types import AppConfig, InjectionId

from .protocols import Hook
from .types import (
    DuplicateHookError,
    HookNotRegisteredError,
    InjectionContext,
    InjectionInvocationError,
)

_HookMap = dict[InjectionId, Hook]


class DefaultFailureInjectionRegistry:
    """Concrete FailureInjectionRegistry; constructed only via factory."""

    def __init__(
        self,
        config: AppConfig,
        *,
        wrap_hook_errors: bool = False,
        on_hook_invoked: Callable[[InjectionId, InjectionContext | None], None] | None = None,
    ) -> None:
        self._config = config
        self._hooks: _HookMap = {}
        self._wrap_hook_errors = wrap_hook_errors
        self._on_hook_invoked = on_hook_invoked
        self._lock = threading.RLock()

    def register_hook(self, injection_id: InjectionId, hook: Hook) -> None:
        if injection_id in self._hooks:
            raise DuplicateHookError(injection_id)
        self._hooks[injection_id] = hook

    def is_active(self, injection_id: InjectionId) -> bool:
        return self._config.is_injection_active(injection_id)

    def invoke_if_active(
        self,
        injection_id: InjectionId,
        *,
        context: InjectionContext | None = None,
    ) -> bool:
        if not self._config.is_injection_active(injection_id):
            return False

        with self._lock:
            hook = self._hooks.get(injection_id)
            if hook is None:
                raise HookNotRegisteredError(injection_id)

        try:
            hook.invoke(context)
        except Exception as exc:
            if self._wrap_hook_errors:
                raise InjectionInvocationError(injection_id, cause=exc) from exc
            raise

        if self._on_hook_invoked is not None:
            self._on_hook_invoked(injection_id, context)

        return True
