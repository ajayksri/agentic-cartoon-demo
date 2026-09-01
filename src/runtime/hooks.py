"""Production failure-injection hook registration (LLD §6.2)."""

from __future__ import annotations

import time
from collections.abc import Callable

from config.types import AppConfig, InjectionId
from failure_injection.protocols import FailureInjectionRegistry
from failure_injection.types import InjectionContext

_DEFAULT_SLOW_DELAY_SECONDS = 0.05

_PRODUCTION_HOOK_IDS: tuple[InjectionId, ...] = (
    InjectionId.FINJ_WKR_PRE,
    InjectionId.FINJ_WKR_POST_AGENT,
    InjectionId.FINJ_WKR_POST_COMMIT,
    InjectionId.FINJ_WKR_PRE_ACK,
    InjectionId.FINJ_Q_DUP,
    InjectionId.FINJ_Q_SLOW,
    InjectionId.FINJ_PRV_TIMEOUT,
    InjectionId.FINJ_PRV_RATE,
    InjectionId.FINJ_PRV_ERROR,
    InjectionId.FINJ_PRV_INVALID,
    InjectionId.FINJ_COORD_DISPATCH,
    InjectionId.FINJ_COORD_CONFLICT,
)


class InjectedFailureError(RuntimeError):
    """Simulated failure when an injection hook is active."""

    def __init__(self, injection_id: InjectionId, message: str) -> None:
        super().__init__(message)
        self.injection_id = injection_id


class ProductionInjectionHook:
    """Thin hook delegating to a shared effect helper."""

    def __init__(self, effect: Callable[[InjectionContext | None], None]) -> None:
        self._effect = effect

    def invoke(self, context: InjectionContext | None = None) -> None:
        self._effect(context)


def _abort(injection_id: InjectionId) -> Callable[[InjectionContext | None], None]:
    def _effect(_context: InjectionContext | None) -> None:
        raise InjectedFailureError(injection_id, f"injected abort for {injection_id.value}")

    return _effect


def _delay(seconds: float) -> Callable[[InjectionContext | None], None]:
    def _effect(_context: InjectionContext | None) -> None:
        time.sleep(seconds)

    return _effect


def _provider_timeout(_context: InjectionContext | None) -> None:
    raise TimeoutError("injected provider timeout")


def _provider_rate_limit(_context: InjectionContext | None) -> None:
    raise InjectedFailureError(InjectionId.FINJ_PRV_RATE, "injected provider rate limit")


def _provider_error(_context: InjectionContext | None) -> None:
    raise InjectedFailureError(InjectionId.FINJ_PRV_ERROR, "injected provider error")


def _provider_invalid(_context: InjectionContext | None) -> None:
    raise InjectedFailureError(InjectionId.FINJ_PRV_INVALID, "injected provider invalid response")


def _coord_dispatch(_context: InjectionContext | None) -> None:
    raise InjectedFailureError(
        InjectionId.FINJ_COORD_DISPATCH,
        "injected outbox publish failure",
    )


def _coord_conflict(_context: InjectionContext | None) -> None:
    from workflow.errors import WorkflowConflictError

    raise WorkflowConflictError("injected coordinator conflict")


def _duplicate(_context: InjectionContext | None) -> None:
    """Simulate duplicate delivery — no abort; task_queue applies redelivery semantics."""


def production_hook_effects() -> dict[InjectionId, Callable[[InjectionContext | None], None]]:
    """Map injection IDs to effect helpers (CG-RT-HLD-003)."""
    return {
        InjectionId.FINJ_WKR_PRE: _abort(InjectionId.FINJ_WKR_PRE),
        InjectionId.FINJ_WKR_POST_AGENT: _abort(InjectionId.FINJ_WKR_POST_AGENT),
        InjectionId.FINJ_WKR_POST_COMMIT: _abort(InjectionId.FINJ_WKR_POST_COMMIT),
        InjectionId.FINJ_WKR_PRE_ACK: _abort(InjectionId.FINJ_WKR_PRE_ACK),
        InjectionId.FINJ_Q_DUP: _duplicate,
        InjectionId.FINJ_Q_SLOW: _delay(_DEFAULT_SLOW_DELAY_SECONDS),
        InjectionId.FINJ_PRV_TIMEOUT: _provider_timeout,
        InjectionId.FINJ_PRV_RATE: _provider_rate_limit,
        InjectionId.FINJ_PRV_ERROR: _provider_error,
        InjectionId.FINJ_PRV_INVALID: _provider_invalid,
        InjectionId.FINJ_COORD_DISPATCH: _coord_dispatch,
        InjectionId.FINJ_COORD_CONFLICT: _coord_conflict,
    }


def register_production_hooks(
    registry: FailureInjectionRegistry,
    *,
    config: AppConfig,
) -> None:
    """Register all twelve FINJ hooks before configure_failure_injection."""
    del config
    effects = production_hook_effects()
    for injection_id in _PRODUCTION_HOOK_IDS:
        registry.register_hook(
            injection_id,
            ProductionInjectionHook(effects[injection_id]),
        )


def production_hook_ids() -> tuple[InjectionId, ...]:
    """Return the stable production hook ID list for tests."""
    return _PRODUCTION_HOOK_IDS
