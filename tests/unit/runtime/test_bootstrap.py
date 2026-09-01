"""Unit tests for RT-006 — SharedBootstrap (LLD §6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from runtime import API_ENTRY, DependencyWiringError

from tests.unit.runtime.helpers import minimal_runtime_config


def test_wire_common_invokes_steps_in_hld_order(spy_bootstrap: MagicMock) -> None:
    """RT-TC-005 / LLD §6.1: observability before queue/workflow creation."""
    from runtime.bootstrap import SharedBootstrap

    SharedBootstrap().wire_common(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
        telemetry=spy_bootstrap.telemetry,
        persistence_factory=spy_bootstrap.persistence_factory,
        queue_factory=spy_bootstrap.queue_factory,
        workflow_factory=spy_bootstrap.workflow_factory,
        failure_injection_factory=spy_bootstrap.failure_injection_factory,
    )

    observed = spy_bootstrap.call_order
    assert observed.index("configure_observability") < observed.index("create_task_queue")
    assert observed.index("configure_observability") < observed.index("create_workflow_engine")
    assert observed.index("register_failure_injection") < observed.index("create_task_queue")


def test_wire_common_registers_failure_injection_before_return() -> None:
    """RT-TC-010 seam: failure injection configured during wire_common."""
    from runtime.bootstrap import SharedBootstrap

    spy = MagicMock()
    SharedBootstrap().wire_common(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
        persistence_factory=spy.persistence_factory,
        queue_factory=spy.queue_factory,
        workflow_factory=spy.workflow_factory,
        failure_injection_factory=spy.failure_injection_factory,
        telemetry=spy.telemetry,
    )

    spy.failure_injection_factory.configure.assert_called_once()


def test_persistence_failure_raises_dependency_wiring_error() -> None:
    """RT-TC-018 seam: wiring failure maps to DependencyWiringError."""
    from runtime.bootstrap import SharedBootstrap

    def _fail_persistence(**_kwargs: object) -> None:
        raise RuntimeError("postgres down")

    with pytest.raises(DependencyWiringError) as exc_info:
        SharedBootstrap().wire_common(
            entry=API_ENTRY,
            config=minimal_runtime_config(),
            persistence_factory=_fail_persistence,
            telemetry=MagicMock(configure=MagicMock()),
        )

    assert exc_info.value.dependency == "persistence"


def test_workflow_engine_factory_receives_no_task_repo(spy_bootstrap: MagicMock) -> None:
    """LLD §6.1: create_workflow_engine uses workflow LLD §1 signature only."""
    from runtime.bootstrap import SharedBootstrap

    workflow_calls: list[dict[str, object]] = []

    def _workflow_factory(**kwargs: object) -> MagicMock:
        workflow_calls.append(kwargs)
        return MagicMock()

    SharedBootstrap().wire_common(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
        telemetry=spy_bootstrap.telemetry,
        persistence_factory=spy_bootstrap.persistence_factory,
        queue_factory=spy_bootstrap.queue_factory,
        workflow_factory=_workflow_factory,
        failure_injection_factory=spy_bootstrap.failure_injection_factory,
    )

    assert workflow_calls
    assert "task_repo" not in workflow_calls[0]


def test_bootstrap_context_retains_redis_connection_manager() -> None:
    """LLD §6.1: redis_connection_manager stored on BootstrapContext."""
    from runtime.bootstrap import SharedBootstrap
    from runtime.fakes.persistence import build_fake_persistence_bundle
    from runtime.fakes.task_queue import FakeConnectionManager

    connection_manager = FakeConnectionManager()
    ctx = SharedBootstrap().wire_common(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
        telemetry=MagicMock(configure=MagicMock()),
        persistence_factory=lambda **_kwargs: build_fake_persistence_bundle(),
        queue_factory=lambda **_kwargs: MagicMock(),
        workflow_factory=lambda **_kwargs: MagicMock(),
        failure_injection_factory=MagicMock(configure=MagicMock()),
        connection_manager=connection_manager,  # type: ignore[arg-type]
    )

    assert ctx.redis_connection_manager is connection_manager


@pytest.fixture
def spy_bootstrap() -> MagicMock:
    """Recording seam for bootstrap order assertions."""
    spy = MagicMock()
    spy.call_order = []

    def _record(name: str):
        def _inner(*_args: object, **_kwargs: object) -> MagicMock:
            spy.call_order.append(name)
            return MagicMock()

        return _inner

    spy.telemetry = MagicMock()
    spy.persistence_factory = _record("create_persistence_stack")
    spy.queue_factory = _record("create_task_queue")
    spy.workflow_factory = _record("create_workflow_engine")
    spy.failure_injection_factory = MagicMock()
    spy.failure_injection_factory.configure = _record("register_failure_injection")
    spy.telemetry.configure = _record("configure_observability")
    return spy
