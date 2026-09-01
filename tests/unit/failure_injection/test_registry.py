"""Pre-code test mold for FINJ-002 — DefaultFailureInjectionRegistry."""

from __future__ import annotations

from typing import cast

import pytest

from config.types import AppConfig, InjectionId
from tests.support.failure_injection_fixtures import stub_app_config

ALL_INJECTION_IDS = tuple(InjectionId)


def test_duplicate_register_raises_duplicate_hook_error() -> None:
    """register_hook duplicate raises DuplicateHookError with injection_id (FINJ-E002)."""
    from failure_injection.fakes import RecordingHook
    from failure_injection.registry import DefaultFailureInjectionRegistry
    from failure_injection.types import DuplicateHookError

    config = cast(AppConfig, stub_app_config())
    registry = DefaultFailureInjectionRegistry(config)
    hook = RecordingHook()

    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)

    with pytest.raises(DuplicateHookError) as exc_info:
        registry.register_hook(InjectionId.FINJ_WKR_PRE, RecordingHook())

    assert exc_info.value.injection_id is InjectionId.FINJ_WKR_PRE
    assert exc_info.value.code == "FINJ-E002"


def test_register_inactive_id_succeeds_cg_finj_hld_002() -> None:
    """register_hook accepts inactive InjectionId; invoke while inactive returns False."""
    from failure_injection.fakes import RecordingHook
    from failure_injection.registry import DefaultFailureInjectionRegistry

    config = cast(AppConfig, stub_app_config(enabled=False))
    registry = DefaultFailureInjectionRegistry(config)
    hook = RecordingHook()

    registry.register_hook(InjectionId.FINJ_PRV_ERROR, hook)
    invoked = registry.invoke_if_active(InjectionId.FINJ_PRV_ERROR)

    assert invoked is False
    assert hook.calls == []


def test_inactive_invoke_returns_false_without_calling_hook() -> None:
    """Inactive invoke_if_active returns False without calling hook (MOD-FINJ-INV-001, 006)."""
    from failure_injection.fakes import RecordingHook
    from failure_injection.registry import DefaultFailureInjectionRegistry

    config = cast(AppConfig, stub_app_config(enabled=False))
    registry = DefaultFailureInjectionRegistry(config)
    hook = RecordingHook()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)

    result = registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert result is False
    assert hook.calls == []


def test_active_unregistered_raises_hook_not_registered_error() -> None:
    """Active ID without hook raises HookNotRegisteredError (FINJ-E003)."""
    from failure_injection.registry import DefaultFailureInjectionRegistry
    from failure_injection.types import HookNotRegisteredError

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_PRV_RATE})),
    )
    registry = DefaultFailureInjectionRegistry(config)

    with pytest.raises(HookNotRegisteredError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_PRV_RATE)

    assert exc_info.value.injection_id is InjectionId.FINJ_PRV_RATE
    assert exc_info.value.code == "FINJ-E003"


def test_active_invoke_calls_hook_once_returns_true() -> None:
    """Active invoke_if_active calls hook once and returns True."""
    from failure_injection.fakes import RecordingHook
    from failure_injection.registry import DefaultFailureInjectionRegistry
    from failure_injection.types import InjectionContext

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = DefaultFailureInjectionRegistry(config)
    hook = RecordingHook()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)
    context = InjectionContext(workflow_id="wf-1", task_id="task-1")

    result = registry.invoke_if_active(InjectionId.FINJ_WKR_PRE, context=context)

    assert result is True
    assert hook.calls == [context]


def test_registry_and_fakes_not_public_exports() -> None:
    """registry.py and fakes.py are not exported from public __init__.py."""
    import failure_injection

    public = set(failure_injection.__all__)
    assert "registry" not in public
    assert "fakes" not in public
    assert "factory" not in public


@pytest.mark.parametrize("injection_id", ALL_INJECTION_IDS)
def test_is_active_matches_stub_is_injection_active(injection_id: InjectionId) -> None:
    """is_active delegates to config.is_injection_active for every InjectionId."""
    from failure_injection.registry import DefaultFailureInjectionRegistry

    active = frozenset({InjectionId.FINJ_WKR_PRE, InjectionId.FINJ_Q_DUP})
    config = cast(AppConfig, stub_app_config(enabled=True, active=active))
    registry = DefaultFailureInjectionRegistry(config)

    assert registry.is_active(injection_id) is config.is_injection_active(injection_id)
