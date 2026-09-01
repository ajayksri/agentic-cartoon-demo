"""Pre-code test mold for WKR-015 — import boundary static analysis (LLD §12.2, WKR-TC-051/052)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_WORKER_SRC = Path(__file__).resolve().parents[3] / "src" / "worker"
_FORBIDDEN_MODULES = frozenset({"api", "cli", "runtime"})
_EVAL_EXEC_PATTERN = re.compile(r"\b(eval|exec)\s*\(")


def _iter_worker_python_files() -> list[Path]:
    if not _WORKER_SRC.exists():
        return []
    return sorted(path for path in _WORKER_SRC.rglob("*.py") if path.is_file())


def _find_forbidden_module_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in _FORBIDDEN_MODULES:
                    violations.append(f"{path.name}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in _FORBIDDEN_MODULES:
                violations.append(f"{path.name}: from {node.module} import ...")
    return violations


def _find_eval_exec_usage(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    violations: list[str] = []
    for match in _EVAL_EXEC_PATTERN.finditer(source):
        violations.append(f"{path.name}: {match.group(0)}")
    return violations


@pytest.mark.wkr_tc("051")
def test_worker_module_has_no_api_cli_runtime_imports() -> None:
    """WKR-TC-051: no imports from api, cli, or runtime in src/worker/."""
    violations: list[str] = []
    for path in _iter_worker_python_files():
        violations.extend(_find_forbidden_module_imports(path))
    assert violations == []


@pytest.mark.wkr_tc("052")
def test_worker_module_has_no_eval_or_exec() -> None:
    """WKR-TC-052: static scan finds no eval( or exec( in src/worker/."""
    violations: list[str] = []
    for path in _iter_worker_python_files():
        violations.extend(_find_eval_exec_usage(path))
    assert violations == []


def test_public_factories_not_exporting_internal_handlers() -> None:
    """interfaces.md §9: handler implementations not exported from __init__.py."""
    init_path = _WORKER_SRC / "__init__.py"
    source = init_path.read_text(encoding="utf-8")
    for forbidden in (
        "CollectTaskHandler",
        "HandlerSupport",
        "DefaultWorkerLoop",
        "RetryClassifier",
    ):
        assert forbidden not in source
