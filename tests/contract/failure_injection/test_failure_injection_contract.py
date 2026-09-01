"""Contract tests CT-FINJ-001 through CT-FINJ-013 (FINJ-005).

Imports ONLY from the failure_injection package public surface.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import cast

import pytest

from config.types import AppConfig, InjectionId
from tests.contract.failure_injection.conftest import InlineRecordingHook
from tests.support.failure_injection_fixtures import stub_app_config

EXPECTED_INJECTION_ID_VALUES: dict[InjectionId, str] = {
    InjectionId.FINJ_WKR_PRE: "FINJ-WKR-PRE",
    InjectionId.FINJ_WKR_POST_AGENT: "FINJ-WKR-POST-AGENT",
    InjectionId.FINJ_WKR_POST_COMMIT: "FINJ-WKR-POST-COMMIT",
    InjectionId.FINJ_WKR_PRE_ACK: "FINJ-WKR-PRE-ACK",
    InjectionId.FINJ_Q_DUP: "FINJ-Q-DUP",
    InjectionId.FINJ_Q_SLOW: "FINJ-Q-SLOW",
    InjectionId.FINJ_PRV_TIMEOUT: "FINJ-PRV-TIMEOUT",
    InjectionId.FINJ_PRV_RATE: "FINJ-PRV-RATE",
    InjectionId.FINJ_PRV_ERROR: "FINJ-PRV-ERROR",
    InjectionId.FINJ_PRV_INVALID: "FINJ-PRV-INVALID",
    InjectionId.FINJ_COORD_DISPATCH: "FINJ-COORD-DISPATCH",
    InjectionId.FINJ_COORD_CONFLICT: "FINJ-COORD-CONFLICT",
}


@pytest.mark.ct_finj("001")
def test_ct_finj_001_registry_bootstrap_same_instance() -> None:
    """CT-FINJ-001: create → configure → get returns same registry instance."""
    import failure_injection

    config = cast(AppConfig, stub_app_config())
    registry = failure_injection.create_failure_injection_registry(config)
    failure_injection.configure_failure_injection(registry)

    assert failure_injection.get_failure_injection_registry() is registry


@pytest.mark.ct_finj("002")
def test_ct_finj_002_unconfigured_accessor_subprocess() -> None:
    """CT-FINJ-002: fresh process get_* without configure raises FINJ-E001."""
    script = """
import failure_injection

try:
    failure_injection.get_failure_injection_registry()
except failure_injection.RegistryNotConfiguredError as exc:
    if exc.code == "FINJ-E001":
        raise SystemExit(42)
    raise
raise SystemExit(1)
"""
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(src_root), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 42, result.stderr


@pytest.mark.ct_finj("003")
def test_ct_finj_003_inactive_injection_no_op() -> None:
    """CT-FINJ-003: enabled=False; hook not called; returns False."""
    import failure_injection

    config = cast(AppConfig, stub_app_config(enabled=False))
    registry = failure_injection.create_failure_injection_registry(config)
    hook = InlineRecordingHook()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)

    result = registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert result is False
    assert hook.calls == []


@pytest.mark.ct_finj("004")
def test_ct_finj_004_active_injection_invokes_hook() -> None:
    """CT-FINJ-004: active FINJ-WKR-PRE invokes hook with context."""
    import failure_injection

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = failure_injection.create_failure_injection_registry(config)
    hook = InlineRecordingHook()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)
    context = failure_injection.InjectionContext(workflow_id="wf-ct4")

    result = registry.invoke_if_active(InjectionId.FINJ_WKR_PRE, context=context)

    assert result is True
    assert hook.calls == [context]


@pytest.mark.ct_finj("005")
def test_ct_finj_005_selective_activation() -> None:
    """CT-FINJ-005: only IDs in active_injections invoke hooks."""
    import failure_injection

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_Q_DUP})),
    )
    registry = failure_injection.create_failure_injection_registry(config)
    active_hook = InlineRecordingHook()
    inactive_hook = InlineRecordingHook()
    registry.register_hook(InjectionId.FINJ_Q_DUP, active_hook)
    registry.register_hook(InjectionId.FINJ_PRV_ERROR, inactive_hook)

    assert registry.invoke_if_active(InjectionId.FINJ_Q_DUP) is True
    assert registry.invoke_if_active(InjectionId.FINJ_PRV_ERROR) is False
    assert len(active_hook.calls) == 1
    assert inactive_hook.calls == []


@pytest.mark.ct_finj("006")
def test_ct_finj_006_duplicate_registration_rejected() -> None:
    """CT-FINJ-006: duplicate register_hook raises DuplicateHookError (FINJ-E002)."""
    import failure_injection

    config = cast(AppConfig, stub_app_config())
    registry = failure_injection.create_failure_injection_registry(config)

    registry.register_hook(InjectionId.FINJ_WKR_PRE, InlineRecordingHook())

    with pytest.raises(failure_injection.DuplicateHookError) as exc_info:
        registry.register_hook(InjectionId.FINJ_WKR_PRE, InlineRecordingHook())

    assert exc_info.value.code == "FINJ-E002"
    assert exc_info.value.injection_id is InjectionId.FINJ_WKR_PRE


@pytest.mark.ct_finj("007")
def test_ct_finj_007_active_unregistered_hook() -> None:
    """CT-FINJ-007: active FINJ-PRV-RATE without hook raises HookNotRegisteredError."""
    import failure_injection

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_PRV_RATE})),
    )
    registry = failure_injection.create_failure_injection_registry(config)

    with pytest.raises(failure_injection.HookNotRegisteredError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_PRV_RATE)

    assert exc_info.value.code == "FINJ-E003"
    assert exc_info.value.injection_id is InjectionId.FINJ_PRV_RATE


@pytest.mark.ct_finj("008")
@pytest.mark.parametrize("injection_id", tuple(InjectionId))
def test_ct_finj_008_is_active_delegation(injection_id: InjectionId) -> None:
    """CT-FINJ-008: is_active matches config.is_injection_active for all twelve IDs."""
    import failure_injection

    active = frozenset({InjectionId.FINJ_WKR_PRE, InjectionId.FINJ_COORD_CONFLICT})
    config = cast(AppConfig, stub_app_config(enabled=True, active=active))
    registry = failure_injection.create_failure_injection_registry(config)

    assert registry.is_active(injection_id) is config.is_injection_active(injection_id)


@pytest.mark.ct_finj("009")
def test_ct_finj_009_injection_id_catalog_and_type_identity() -> None:
    """CT-FINJ-009: twelve members, string values, config/failure_injection type identity."""
    from config.types import InjectionId as ConfigInjectionId

    import failure_injection

    assert ConfigInjectionId is failure_injection.InjectionId
    assert len(failure_injection.InjectionId) == 12
    for member, expected_value in EXPECTED_INJECTION_ID_VALUES.items():
        assert failure_injection.InjectionId(expected_value) is member
        assert member.value == expected_value


@pytest.mark.ct_finj("010")
def test_ct_finj_010_no_forbidden_imports() -> None:
    """CT-FINJ-010: src/failure_injection has no forbidden cross-module imports."""
    assert _find_forbidden_failure_injection_imports() == []


@pytest.mark.ct_finj("011")
def test_ct_finj_011_in_memory_protocol_doubles_callable() -> None:
    """CT-FINJ-011: custom Hook and FailureInjectionRegistry doubles are callable."""
    import failure_injection

    hook = InlineRecordingHook()
    registry = _InMemoryFailureInjectionRegistry()

    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)
    registry.set_active(InjectionId.FINJ_WKR_PRE, True)
    context = failure_injection.InjectionContext(workflow_id="wf-ct11")

    assert registry.invoke_if_active(InjectionId.FINJ_WKR_PRE, context=context) is True
    assert hook.calls == [context]
    assert registry.is_active(InjectionId.FINJ_WKR_PRE) is True


@pytest.mark.ct_finj("012")
def test_ct_finj_012_enabled_false_ignores_active_list() -> None:
    """CT-FINJ-012: enabled=False with non-empty active list does not invoke hook."""
    import failure_injection

    config = cast(
        AppConfig,
        stub_app_config(
            enabled=False,
            active=frozenset({InjectionId.FINJ_WKR_PRE}),
        ),
    )
    registry = failure_injection.create_failure_injection_registry(config)
    hook = InlineRecordingHook()
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)

    result = registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert result is False
    assert hook.calls == []


@pytest.mark.ct_finj("013")
def test_ct_finj_013_hook_exception_raw_propagation() -> None:
    """CT-FINJ-013: default registry propagates same ValueError instance unchanged."""
    import failure_injection

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_WKR_PRE})),
    )
    registry = failure_injection.create_failure_injection_registry(config)
    original = ValueError("contract raw propagation")
    hook = InlineRecordingHook(raise_on_invoke=original)
    registry.register_hook(InjectionId.FINJ_WKR_PRE, hook)

    with pytest.raises(ValueError) as exc_info:
        registry.invoke_if_active(InjectionId.FINJ_WKR_PRE)

    assert exc_info.value is original


def _find_forbidden_failure_injection_imports() -> list[str]:
    """AST scan for forbidden cross-module imports under src/failure_injection."""
    import ast
    from pathlib import Path

    forbidden_roots = {"workflow", "worker", "agents", "api", "persistence"}
    src_root = Path(__file__).resolve().parents[3] / "src" / "failure_injection"
    violations: list[str] = []

    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in forbidden_roots:
                        violations.append(f"{path.relative_to(src_root)}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                root = node.module.split(".")[0]
                if root in forbidden_roots:
                    violations.append(
                        f"{path.relative_to(src_root)}: from {node.module} import ..."
                    )

    return violations


@dataclass
class _InMemoryFailureInjectionRegistry:
    """Lightweight FailureInjectionRegistry double for CT-FINJ-011."""

    _hooks: dict[InjectionId, InlineRecordingHook] = field(default_factory=dict)
    _active: set[InjectionId] = field(default_factory=set)

    def register_hook(self, injection_id: InjectionId, hook: InlineRecordingHook) -> None:
        if injection_id in self._hooks:
            from failure_injection import DuplicateHookError

            raise DuplicateHookError(injection_id)
        self._hooks[injection_id] = hook

    def is_active(self, injection_id: InjectionId) -> bool:
        return injection_id in self._active

    def set_active(self, injection_id: InjectionId, active: bool) -> None:
        if active:
            self._active.add(injection_id)
        else:
            self._active.discard(injection_id)

    def invoke_if_active(
        self,
        injection_id: InjectionId,
        *,
        context=None,
    ) -> bool:
        if not self.is_active(injection_id):
            return False
        hook = self._hooks.get(injection_id)
        if hook is None:
            from failure_injection import HookNotRegisteredError

            raise HookNotRegisteredError(injection_id)
        hook.invoke(context)
        return True
