"""Unit tests for RT-014 — WorkerProcessWiring."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from runtime import WORKER_ENTRY
from runtime.bootstrap import BootstrapContext
from runtime.fakes.persistence import build_fake_persistence_bundle
from runtime.fakes.task_queue import FakeConnectionManager
from runtime.telemetry import RecordingRuntimeTelemetry
from runtime.types import ProcessKind, WiredDependencies
from runtime.wiring.worker import WorkerProcessWiring, WorkerProductionDependencies
from tests.unit.runtime.helpers import minimal_runtime_config


def test_worker_wiring_uses_injectable_dependencies_and_loop_factory() -> None:
    ctx = _bootstrap_context()
    loop = object()

    def _deps_factory(**_kwargs: object) -> WorkerProductionDependencies:
        return WorkerProductionDependencies(
            registry=object(),
            idempotency_orchestrator=object(),
            collector=object(),
            topic_selection_agent=object(),
            scenario_generation_agent=object(),
            critic_agent=object(),
            model_provider_factory=lambda *_args, **_kwargs: object(),
        )

    wired = WorkerProcessWiring().wire(
        ctx,
        worker_dependencies_factory=_deps_factory,
        worker_loop_factory=lambda **_kwargs: loop,
    )

    assert wired.wired.worker_loop is loop
    assert wired.wired.api_router is None
    assert wired.wired.outbox_publisher is None


def test_worker_wiring_module_has_no_forbidden_imports() -> None:
    module_path = Path(__file__).resolve().parents[3] / "src" / "runtime" / "wiring" / "worker.py"
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


def test_default_worker_dependencies_factory_delegates_to_worker_export() -> None:
    """Runtime wiring must delegate production assembly to worker public factory."""
    from persistence.fakes.idempotency import InMemoryIdempotencyRepo
    from persistence.fakes.transaction import InMemoryTransactionManager
    from runtime.wiring.worker import _default_worker_dependencies_factory

    from tests.contract.worker.helpers import minimal_worker_config

    class _PersistenceBundleStub:
        def __init__(self, idempotency_repo: object) -> None:
            self.idempotency_repo = idempotency_repo

    config = minimal_worker_config()
    txn = InMemoryTransactionManager()
    bundle = _PersistenceBundleStub(
        InMemoryIdempotencyRepo(transaction_manager=txn),
    )

    runtime_prod = _default_worker_dependencies_factory(
        entry=object(),
        config=config,
        persistence_bundle=bundle,
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
    )

    assert runtime_prod.registry is not None
    assert runtime_prod.model_provider_factory is not None


def _bootstrap_context() -> BootstrapContext:
    config = minimal_runtime_config()
    return BootstrapContext(
        entry=WORKER_ENTRY,
        config=config,
        bundle=build_fake_persistence_bundle(),
        task_queue=MagicMock(),
        redis_connection_manager=FakeConnectionManager(),  # type: ignore[arg-type]
        workflow_engine=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        telemetry=RecordingRuntimeTelemetry(process_kind=ProcessKind.WORKER),
        wired=WiredDependencies(entry=WORKER_ENTRY, config=config),
    )
