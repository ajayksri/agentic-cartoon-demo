"""Pre-code test mold for FINJ-002 — UT-FINJ-001 hook exception wrap path."""

from __future__ import annotations

from typing import cast

import pytest

from config.types import AppConfig, InjectionId
from tests.support.failure_injection_fixtures import stub_app_config


class _RaisingHook:
    """Hook that raises a stored exception on invoke."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def invoke(self, context: object = None) -> None:
        raise self._exc


def test_ut_finj_001_wrap_hook_errors_wraps_exception_with_cause() -> None:
    """UT-FINJ-001: wrap_hook_errors=True wraps Exception as InjectionInvocationError."""
    from failure_injection.registry import DefaultFailureInjectionRegistry
    from failure_injection.types import InjectionInvocationError

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = DefaultFailureInjectionRegistry(config, wrap_hook_errors=True)
    original = ValueError("hook failure")
    registry.register_hook(InjectionId.FINJ_WKR_PRE, _RaisingHook(original))

    with pytest.raises(InjectionInvocationError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    wrapped = exc_info.value
    assert wrapped.code == "FINJ-E004"
    assert wrapped.injection_id is InjectionId.FINJ_WKR_PRE
    assert wrapped.cause is original
    assert wrapped.__cause__ is original


def test_ut_finj_001_wrap_hook_errors_false_propagates_same_exception() -> None:
    """UT-FINJ-001 / CT-FINJ-013: default path re-raises same Exception instance."""
    from failure_injection.registry import DefaultFailureInjectionRegistry

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = DefaultFailureInjectionRegistry(config, wrap_hook_errors=False)
    original = ValueError("hook failure")
    registry.register_hook(InjectionId.FINJ_WKR_PRE, _RaisingHook(original))

    with pytest.raises(ValueError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert exc_info.value is original


def test_ut_finj_001_wrap_hook_errors_does_not_wrap_base_exception() -> None:
    """UT-FINJ-001: BaseException subclasses propagate unchanged when wrap_hook_errors=True."""
    from failure_injection.registry import DefaultFailureInjectionRegistry

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = DefaultFailureInjectionRegistry(config, wrap_hook_errors=True)
    original = KeyboardInterrupt()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, _RaisingHook(original))

    with pytest.raises(KeyboardInterrupt) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert exc_info.value is original
