"""Shared contract-test helpers for runtime module (RT-018, LLD §21)."""

from __future__ import annotations

import sys
import ast
import inspect
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from config.types import AppConfig

from tests.contract.worker.helpers import minimal_worker_config

_FORBIDDEN_IMPORT_PREFIXES = ("agents", "collector", "providers", "cli")
_ALLOWED_DEPENDENCY_PREFIXES = (
    "config",
    "observability",
    "failure_injection",
    "persistence",
    "task_queue",
    "workflow",
    "worker",
    "api",
    "runtime",
)
_PUBLIC_MODULE_NAMES = ("types.py", "errors.py", "protocols.py", "__init__.py")
_EFMS_TOKENS = ("efms_", "efms", "EFMS")
_ENV_READ_PATTERNS = ("load_dotenv", "dotenv", 'open(".env"', "open('.env'")
_STDLIB_MODULE_NAMES = frozenset(getattr(sys, "stdlib_module_names", set()))
_EXTRA_ALLOWED_ROOTS = frozenset(
    {
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "collections",
        "contextlib",
        "threading",
        "signal",
        "socket",
        "os",
        "asyncio",
        "functools",
        "abc",
        "pathlib",
        "logging",
        "uvicorn",
        "fastapi",
        "__future__",
        "types",
        "time",
        "importlib",
        "unittest",
    }
)


def _is_allowed_import_root(root: str) -> bool:
    if root in _ALLOWED_DEPENDENCY_PREFIXES:
        return True
    if root in _EXTRA_ALLOWED_ROOTS:
        return True
    if root in _STDLIB_MODULE_NAMES:
        return True
    return root.startswith("_")


def static_scan_allowed_import_roots(package_root: Path) -> list[str]:
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if not _is_allowed_import_root(root):
                        violations.append(f"{path.name}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    root = node.module.split(".", 1)[0]
                    if not _is_allowed_import_root(root):
                        violations.append(f"{path.name}:{node.module}")
    return violations


def minimal_runtime_config(**kwargs: Any) -> AppConfig:
    """Validated AppConfig for runtime contract tests."""
    return minimal_worker_config(**kwargs)


def runtime_public_module_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[3] / "src" / "runtime"
    return [root / name for name in _PUBLIC_MODULE_NAMES]


def read_public_module_sources() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in runtime_public_module_paths())


def static_scan_forbidden_imports(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in _FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in _FORBIDDEN_IMPORT_PREFIXES:
                violations.append(node.module)
    return violations


def assert_error_message_excludes_secrets(error: BaseException) -> None:
    message = str(error).lower()
    forbidden = ("password=", "api_key", "secret", "token=", "postgresql://")
    for fragment in forbidden:
        assert fragment not in message


@dataclass
class RecordingCallOrder:
    calls: list[str]

    def record(self, name: str) -> None:
        self.calls.append(name)


class FakeWorkflowEngine:
    """Minimal workflow engine spy for RT-TC-009."""

    def __init__(self) -> None:
        self.reconcile_calls: list[tuple[Any, ...]] = []

    def reconcile_stuck_workflows(self, *args: Any, **kwargs: Any) -> object:
        self.reconcile_calls.append((args, kwargs))
        return object()


class FakeWorkerLoop:
    """Minimal worker loop spy for RT-TC-017."""

    def __init__(self) -> None:
        self.stop_calls = 0

    def run(self) -> None:
        return None

    def stop(self) -> None:
        self.stop_calls += 1


class StubOutboxPublisherLoop:
    """Protocol stub for RT-TC-014/016."""

    def __init__(self) -> None:
        self._stopped = False

    def run(self) -> None:
        return None

    def stop(self) -> None:
        self._stopped = True


def public_export_names(module: ModuleType) -> frozenset[str]:
    exports = getattr(module, "__all__", None)
    if exports is None:
        return frozenset(name for name in dir(module) if not name.startswith("_"))
    return frozenset(exports)


def dataclass_field_names(cls: type[Any]) -> tuple[str, ...]:
    if not is_dataclass(cls):
        return ()
    return tuple(field.name for field in fields(cls))


def simulate_worker_shutdown(*, worker_loop: FakeWorkerLoop, teardown: Any) -> None:
    """RT-TC-017 seam: stop worker loop before connection teardown (LLD §14)."""
    from runtime.runners import run_worker_shutdown_sequence

    run_worker_shutdown_sequence(worker_loop=worker_loop, teardown=teardown)


def entry_function_parameters(function: Any) -> Sequence[inspect.Parameter]:
    return tuple(inspect.signature(function).parameters.values())
