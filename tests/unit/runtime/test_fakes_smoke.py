"""Smoke tests for RT-016 — runtime fakes."""

from __future__ import annotations

from runtime import API_ENTRY
from runtime.fakes import (
    FakeCompositionRoot,
    FakeConnectionManager,
    FakePersistenceBundle,
    FakeTaskQueue,
    FakeWorkerLoop,
    FakeWorkflowEngine,
    RecordingCallOrder,
)
from tests.unit.runtime.helpers import minimal_runtime_config


def test_fake_worker_loop_records_stop() -> None:
    loop = FakeWorkerLoop()
    loop.run()
    loop.stop()
    loop.stop()

    assert loop.run_calls == 1
    assert loop.stop_calls == 2


def test_fake_workflow_engine_records_reconcile() -> None:
    engine = FakeWorkflowEngine()
    config = minimal_runtime_config()

    engine.reconcile_stuck_workflows(config=config, batch_size=50)

    assert len(engine.reconcile_calls) == 1
    assert engine.reconcile_calls[0]["batch_size"] == 50


def test_fake_connection_manager_ping_and_close() -> None:
    manager = FakeConnectionManager(ping_ok=True)
    manager.ping()
    manager.close()

    assert manager.ping_calls == 1
    assert manager.closed is True


def test_fake_persistence_bundle_health_check() -> None:
    bundle = FakePersistenceBundle.create(health_ok=True)
    bundle.pool_manager.health_check()

    assert bundle.pool_manager.health_check_calls == 1


def test_fake_composition_root_records_bootstrap_order() -> None:
    config = minimal_runtime_config()
    root = FakeCompositionRoot(config=config)

    root.bootstrap(API_ENTRY)
    order = RecordingCallOrder()
    order.record("configure_observability")
    order.record("worker_loop_start")

    assert root.call_order.calls == ["bootstrap:api"]
    assert order.calls == ["configure_observability", "worker_loop_start"]


def test_fake_task_queue_is_reused_worker_fake() -> None:
    queue = FakeTaskQueue()
    assert queue.pending == []
    assert queue.acked == []
