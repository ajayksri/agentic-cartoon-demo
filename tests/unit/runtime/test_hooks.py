"""Unit tests for RT-004 — register_production_hooks."""

from __future__ import annotations

import ast
from pathlib import Path

from config.types import InjectionId
from failure_injection.factory import build_failure_injection_registry

from runtime.hooks import production_hook_ids, register_production_hooks
from tests.unit.runtime.helpers import minimal_runtime_config


def test_registers_all_twelve_production_hooks() -> None:
    config = minimal_runtime_config()
    registry = build_failure_injection_registry(config)

    register_production_hooks(registry, config=config)

    registered = set(getattr(registry, "_hooks").keys())
    assert registered == set(production_hook_ids())
    assert len(registered) == 12


def test_production_hook_ids_match_lld_table() -> None:
    expected = {
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
    }
    assert set(production_hook_ids()) == expected
    assert len(production_hook_ids()) == len(set(production_hook_ids()))


def test_hooks_module_has_no_forbidden_imports() -> None:
    module_path = Path(__file__).resolve().parents[3] / "src" / "runtime" / "hooks.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden = {"agents", "collector", "providers", "cli"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in forbidden
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in forbidden


def test_finj_q_dup_uses_duplicate_effect_not_abort() -> None:
    """RT-004-R001: FINJ_Q_DUP simulates duplicate delivery without abort."""
    from runtime.hooks import production_hook_effects

    effect = production_hook_effects()[InjectionId.FINJ_Q_DUP]
    effect(None)  # no-op duplicate — must not raise


def test_inactive_production_hook_is_no_op() -> None:
    """RT-004-R002: inactive invoke returns False without executing hook."""
    config = minimal_runtime_config()
    registry = build_failure_injection_registry(config)
    register_production_hooks(registry, config=config)

    assert registry.invoke_if_active(InjectionId.FINJ_Q_DUP) is False
