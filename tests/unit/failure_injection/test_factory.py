"""Pre-code test mold for FINJ-003 — registry factory."""

from __future__ import annotations

from typing import cast

import pytest

from config.types import AppConfig, InjectionId
from tests.support.failure_injection_fixtures import stub_app_config


class _RaisingHook:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def invoke(self, context: object = None) -> None:
        raise self._exc


def test_build_failure_injection_registry_returns_empty_hook_map() -> None:
    """build_failure_injection_registry returns registry with no registered hooks."""
    from failure_injection.factory import build_failure_injection_registry
    from failure_injection.types import HookNotRegisteredError

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = build_failure_injection_registry(config)

    with pytest.raises(HookNotRegisteredError):
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)


def test_build_failure_injection_registry_wrap_hook_errors_forwards_flag() -> None:
    """build_failure_injection_registry(..., wrap_hook_errors=True) matches UT-FINJ-001."""
    from failure_injection.factory import build_failure_injection_registry
    from failure_injection.types import InjectionInvocationError

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = build_failure_injection_registry(config, wrap_hook_errors=True)
    original = ValueError("factory wrap path")
    registry.register_hook(InjectionId.FINJ_WKR_PRE, _RaisingHook(original))

    with pytest.raises(InjectionInvocationError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert exc_info.value.cause is original
    assert exc_info.value.__cause__ is original


def test_create_failure_injection_registry_does_not_configure_singleton() -> None:
    """Public factory constructs registry without binding process singleton."""
    from failure_injection import RegistryNotConfiguredError, get_failure_injection_registry
    from failure_injection.factory import create_failure_injection_registry

    config = cast(AppConfig, stub_app_config())
    registry = create_failure_injection_registry(config)

    assert registry is not None

    with pytest.raises(RegistryNotConfiguredError) as exc_info:
        get_failure_injection_registry()

    assert exc_info.value.code == "FINJ-E001"
