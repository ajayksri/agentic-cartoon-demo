"""Smoke tests for failure_injection public types (FINJ-001)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from config.types import InjectionId as ConfigInjectionId
from failure_injection.types import (
    DuplicateHookError,
    FailureInjectionError,
    HookNotRegisteredError,
    InjectionContext,
    InjectionId,
    InjectionInvocationError,
    RegistryNotConfiguredError,
)

# Authoritative catalog: docs/architecture/failure-model.md §4
FAILURE_MODEL_INJECTION_IDS = frozenset(
    {
        "FINJ-WKR-PRE",
        "FINJ-WKR-POST-AGENT",
        "FINJ-WKR-POST-COMMIT",
        "FINJ-WKR-PRE-ACK",
        "FINJ-Q-DUP",
        "FINJ-Q-SLOW",
        "FINJ-PRV-TIMEOUT",
        "FINJ-PRV-RATE",
        "FINJ-PRV-ERROR",
        "FINJ-PRV-INVALID",
        "FINJ-COORD-DISPATCH",
        "FINJ-COORD-CONFLICT",
    }
)


def test_injection_id_is_config_types_identity() -> None:
    assert InjectionId is ConfigInjectionId


def test_injection_id_member_count() -> None:
    assert len(InjectionId) == 12


def test_injection_id_values_match_failure_model() -> None:
    assert {member.value for member in InjectionId} == FAILURE_MODEL_INJECTION_IDS


def test_failure_injection_error_subclasses() -> None:
    assert issubclass(RegistryNotConfiguredError, FailureInjectionError)
    assert issubclass(DuplicateHookError, FailureInjectionError)
    assert issubclass(HookNotRegisteredError, FailureInjectionError)
    assert issubclass(InjectionInvocationError, FailureInjectionError)


def test_error_codes() -> None:
    assert RegistryNotConfiguredError.code == "FINJ-E001"
    assert DuplicateHookError.code == "FINJ-E002"
    assert HookNotRegisteredError.code == "FINJ-E003"
    assert InjectionInvocationError.code == "FINJ-E004"


def test_duplicate_hook_error_injection_id_attr() -> None:
    exc = DuplicateHookError(InjectionId.FINJ_WKR_PRE)
    assert exc.injection_id is InjectionId.FINJ_WKR_PRE
    assert exc.code == "FINJ-E002"


def test_hook_not_registered_error_injection_id_attr() -> None:
    exc = HookNotRegisteredError(InjectionId.FINJ_Q_DUP)
    assert exc.injection_id is InjectionId.FINJ_Q_DUP
    assert exc.code == "FINJ-E003"


def test_injection_invocation_error_attrs() -> None:
    cause = ValueError("hook failed")
    exc = InjectionInvocationError(InjectionId.FINJ_PRV_ERROR, cause=cause)
    assert exc.injection_id is InjectionId.FINJ_PRV_ERROR
    assert exc.cause is cause
    assert exc.code == "FINJ-E004"


def test_injection_context_is_frozen() -> None:
    ctx = InjectionContext(workflow_id="wf-1")
    with pytest.raises(FrozenInstanceError):
        ctx.workflow_id = "wf-2"  # type: ignore[misc]
