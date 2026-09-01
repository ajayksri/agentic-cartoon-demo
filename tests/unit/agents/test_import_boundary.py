"""Pre-code test mold for AGT-001 — jsonschema pin and import boundary (LLD §3, §5)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest


_AGENTS_SRC = Path(__file__).resolve().parents[3] / "src" / "agents"
_PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"
_JSONSCHEMA_SPEC = (">=4.20.0", "<5")
_FORBIDDEN_MODULES = frozenset({"worker", "workflow", "persistence", "task_queue"})


def _iter_agent_python_files(*, exclude_validation: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted(_AGENTS_SRC.rglob("*.py")):
        rel = path.relative_to(_AGENTS_SRC)
        if exclude_validation and rel.parts and rel.parts[0] == "validation":
            continue
        files.append(path)
    return files


def _find_jsonschema_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "jsonschema" or alias.name.startswith("jsonschema."):
                    violations.append(f"{path.name}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "jsonschema" or node.module.startswith("jsonschema."):
                violations.append(f"{path.name}: from {node.module} import ...")
    return violations


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


def _dependency_specs() -> dict[str, str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    specs: dict[str, str] = {}
    for dep in data["project"]["dependencies"]:
        name = re.split(r"[<>=!]", dep, maxsplit=1)[0].strip()
        specs[name] = dep
    return specs


def test_jsonschema_dependency_declared_in_pyproject() -> None:
    """LLD §5: jsonschema pin declares minimum >=4.20.0 and upper bound <5."""
    specs = _dependency_specs()
    minimum, upper = _JSONSCHEMA_SPEC
    assert "jsonschema" in specs, "missing jsonschema dependency"
    spec = specs["jsonschema"]
    assert minimum in spec, f"jsonschema missing minimum bound {minimum}"
    assert upper in spec, f"jsonschema missing upper bound {upper}"


def test_non_validation_modules_have_no_jsonschema_imports() -> None:
    """jsonschema imports allowed only under src/agents/validation/ (LLD §5)."""
    violations: list[str] = []
    for path in _iter_agent_python_files(exclude_validation=True):
        violations.extend(_find_jsonschema_imports(path))
    assert violations == []


def test_validation_subpackage_may_import_jsonschema() -> None:
    """When validation/schema.py exists it may import jsonschema."""
    schema_path = _AGENTS_SRC / "validation" / "schema.py"
    if not schema_path.exists():
        pytest.skip("validation/schema.py not yet implemented")
    source = schema_path.read_text(encoding="utf-8")
    assert "jsonschema" in source


def test_agents_module_has_no_forbidden_cross_module_imports() -> None:
    """AGT-TC-060 scaffold: no worker/workflow/persistence/task_queue imports."""
    violations: list[str] = []
    for path in _iter_agent_python_files(exclude_validation=False):
        violations.extend(_find_forbidden_module_imports(path))
    assert violations == []
