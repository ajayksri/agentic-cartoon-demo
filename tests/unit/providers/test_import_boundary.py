"""Pre-code test mold for PRV-001 — vendor SDK import boundary (LLD §5, §15.2)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest
_VENDOR_SDK_MODULES = frozenset({"openai", "anthropic", "google.genai", "google.generativeai"})
_PROVIDERS_SRC = Path(__file__).resolve().parents[3] / "src" / "providers"
_PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"
def _iter_provider_python_files(*, exclude_vendors: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted(_PROVIDERS_SRC.rglob("*.py")):
        rel = path.relative_to(_PROVIDERS_SRC)
        if exclude_vendors and rel.parts and rel.parts[0] == "vendors":
            continue
        files.append(path)
    return files
def _find_forbidden_vendor_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if alias.name in _VENDOR_SDK_MODULES or root in {"openai", "anthropic", "google"}:
                    violations.append(f"{path.name}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if node.module in _VENDOR_SDK_MODULES or root in {"openai", "anthropic", "google"}:
                violations.append(f"{path.name}: from {node.module} import ...")
    return violations
_SDK_PIN_SPECS: dict[str, tuple[str, str]] = {
    "openai": (">=1.55.0", "<2"),
    "anthropic": (">=0.45.0", "<1"),
    "google-genai": (">=2.0.0", "<3"),
}
def _dependency_specs() -> dict[str, str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    specs: dict[str, str] = {}
    for dep in data["project"]["dependencies"]:
        name = re.split(r"[<>=!]", dep, maxsplit=1)[0].strip()
        specs[name] = dep
    return specs
def test_sdk_dependencies_declared_in_pyproject() -> None:
    """LLD §5: SDK pins declare minimum and upper bounds per package."""
    specs = _dependency_specs()

    for package, (minimum, upper) in _SDK_PIN_SPECS.items():
        assert package in specs, f"missing dependency pin for {package}"
        spec = specs[package]
        assert minimum in spec, f"{package} missing minimum bound {minimum}"
        assert upper in spec, f"{package} missing upper bound {upper}"
def test_public_surface_does_not_export_vendors() -> None:
    """CG-PRV-HLD-001: vendors subtree is not part of the public providers surface."""
    import providers

    assert "vendors" not in providers.__all__
    assert "vendors" not in dir(providers)
def test_non_vendor_modules_have_no_sdk_imports() -> None:
    """Non-vendors provider modules MUST NOT import vendor SDK packages."""
    violations: list[str] = []
    for path in _iter_provider_python_files(exclude_vendors=True):
        violations.extend(_find_forbidden_vendor_imports(path))
    assert violations == []
def test_vendors_subpackage_isolated_from_public_init() -> None:
    """Public __init__.py must not re-export or import vendors package."""
    init_path = _PROVIDERS_SRC / "__init__.py"
    violations = _find_forbidden_vendor_imports(init_path)
    source = init_path.read_text(encoding="utf-8")
    assert "vendors" not in source
    assert violations == []
