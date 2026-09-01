"""Unit tests for RT-007 — DefaultOutboxPublisherLoop (LLD §11.2)."""

from __future__ import annotations

import threading

from runtime import OutboxPublisherConfig, OutboxPublisherLoop

from runtime.outbox import DefaultOutboxPublisherLoop


def test_outbox_publisher_loop_protocol_exposes_run_and_stop() -> None:
    """RT-TC-014: protocol methods present on implementation."""
    loop = DefaultOutboxPublisherLoop(
        config=object(),  # type: ignore[arg-type]
        publisher_config=OutboxPublisherConfig(),
        outbox_repo=object(),  # type: ignore[arg-type]
        workflow_repo=object(),  # type: ignore[arg-type]
        task_queue=object(),  # type: ignore[arg-type]
        failure_injection=object(),  # type: ignore[arg-type]
        message_builder=object(),  # type: ignore[arg-type]
        telemetry=object(),  # type: ignore[arg-type]
        shutdown=threading.Event(),
    )

    assert hasattr(loop, "run")
    assert hasattr(loop, "stop")
    assert callable(getattr(OutboxPublisherLoop, "run", None) or loop.run)
    assert callable(getattr(OutboxPublisherLoop, "stop", None) or loop.stop)


def test_stop_is_idempotent() -> None:
    """RT-TC-016: repeated stop() calls do not raise."""
    shutdown = threading.Event()
    loop = DefaultOutboxPublisherLoop(
        config=object(),  # type: ignore[arg-type]
        publisher_config=OutboxPublisherConfig(),
        outbox_repo=object(),  # type: ignore[arg-type]
        workflow_repo=object(),  # type: ignore[arg-type]
        task_queue=object(),  # type: ignore[arg-type]
        failure_injection=object(),  # type: ignore[arg-type]
        message_builder=object(),  # type: ignore[arg-type]
        telemetry=object(),  # type: ignore[arg-type]
        shutdown=shutdown,
    )

    loop.stop()
    loop.stop()

    assert shutdown.is_set()


def test_publish_batch_never_calls_workflow_engine_mutations() -> None:
    """MOD-RT-INV-012: publish path does not invoke workflow transitions."""
    engine = _RecordingWorkflowEngine()
    loop = DefaultOutboxPublisherLoop(
        config=object(),  # type: ignore[arg-type]
        publisher_config=OutboxPublisherConfig(),
        outbox_repo=_EmptyOutboxRepo(),
        workflow_repo=object(),  # type: ignore[arg-type]
        task_queue=_AcceptingQueue(),
        workflow_engine=engine,
        failure_injection=_NoOpFailureInjection(),
        message_builder=_NoOpBuilder(),
        telemetry=_NoOpTelemetry(),
        shutdown=threading.Event(),
    )

    loop._publish_batch()  # type: ignore[attr-defined]

    assert engine.transition_calls == []


class _RecordingWorkflowEngine:
    def __init__(self) -> None:
        self.transition_calls: list[object] = []

    def apply_transition(self, *_args: object, **_kwargs: object) -> None:
        self.transition_calls.append((_args, _kwargs))


class _EmptyOutboxRepo:
    def fetch_unpublished(self, limit: int) -> list[object]:
        del limit
        return []


class _AcceptingQueue:
    def enqueue(self, *_args: object, **_kwargs: object) -> None:
        return None


class _NoOpFailureInjection:
    def invoke_if_active(self, *_args: object, **_kwargs: object) -> None:
        return None


class _NoOpBuilder:
    def build(self, _entry: object) -> object:
        return object()


class _NoOpTelemetry:
    def emit_outbox_batch(self, _result: object) -> None:
        return None
