"""Pre-code test mold for FINJ-004 — singleton bootstrap and public exports."""

from __future__ import annotations

from typing import cast

import pytest

from config.types import AppConfig
from tests.support.failure_injection_fixtures import stub_app_config


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Isolate singleton state between tests via private reset hook."""
    import failure_injection

    failure_injection._reset_failure_injection_state()
    yield
    failure_injection._reset_failure_injection_state()


def test_create_configure_get_returns_same_instance() -> None:
    """CT-FINJ-001 unit seam: create → configure → get returns same registry."""
    import failure_injection

    config = cast(AppConfig, stub_app_config())
    registry = failure_injection.create_failure_injection_registry(config)
    failure_injection.configure_failure_injection(registry)

    assert failure_injection.get_failure_injection_registry() is registry


def test_get_before_configure_raises_registry_not_configured_error() -> None:
    """get_failure_injection_registry before configure raises FINJ-E001."""
    import failure_injection

    with pytest.raises(failure_injection.RegistryNotConfiguredError) as exc_info:
        failure_injection.get_failure_injection_registry()

    assert exc_info.value.code == "FINJ-E001"


def test_create_without_configure_does_not_bind_singleton() -> None:
    """create_failure_injection_registry alone does not configure singleton."""
    import failure_injection

    config = cast(AppConfig, stub_app_config())
    failure_injection.create_failure_injection_registry(config)

    with pytest.raises(failure_injection.RegistryNotConfiguredError):
        failure_injection.get_failure_injection_registry()


EXPECTED_PUBLIC_EXPORTS = frozenset(
    {
        "__version__",
        "InjectionId",
        "InjectionContext",
        "Hook",
        "FailureInjectionRegistry",
        "FailureInjectionError",
        "RegistryNotConfiguredError",
        "DuplicateHookError",
        "HookNotRegisteredError",
        "InjectionInvocationError",
        "create_failure_injection_registry",
        "configure_failure_injection",
        "get_failure_injection_registry",
    }
)


def test_all_matches_lld_public_export_table() -> None:
    """__all__ matches LLD §1.2 exactly (no internal modules)."""
    import failure_injection

    assert frozenset(failure_injection.__all__) == EXPECTED_PUBLIC_EXPORTS


def test_documented_public_symbols_importable() -> None:
    """from failure_injection import (...) resolves all documented public symbols."""
    from failure_injection import (
        __version__,
        DuplicateHookError,
        FailureInjectionError,
        FailureInjectionRegistry,
        Hook,
        HookNotRegisteredError,
        InjectionContext,
        InjectionId,
        InjectionInvocationError,
        RegistryNotConfiguredError,
        configure_failure_injection,
        create_failure_injection_registry,
        get_failure_injection_registry,
    )

    assert isinstance(__version__, str)
    assert issubclass(FailureInjectionError, Exception)
    assert issubclass(RegistryNotConfiguredError, FailureInjectionError)
    assert issubclass(DuplicateHookError, FailureInjectionError)
    assert issubclass(HookNotRegisteredError, FailureInjectionError)
    assert issubclass(InjectionInvocationError, FailureInjectionError)
    assert InjectionId is not None
    assert InjectionContext is not None
    assert Hook is not None
    assert FailureInjectionRegistry is not None
    assert callable(create_failure_injection_registry)
    assert callable(configure_failure_injection)
    assert callable(get_failure_injection_registry)


def test_reset_failure_injection_state_clears_registry() -> None:
    """_reset_failure_injection_state clears configured singleton."""
    import failure_injection

    config = cast(AppConfig, stub_app_config())
    registry = failure_injection.create_failure_injection_registry(config)
    failure_injection.configure_failure_injection(registry)
    assert failure_injection.get_failure_injection_registry() is registry

    failure_injection._reset_failure_injection_state()

    with pytest.raises(failure_injection.RegistryNotConfiguredError):
        failure_injection.get_failure_injection_registry()
