"""Smoke tests for WKR-016 worker fakes."""

from __future__ import annotations

import pytest

from datetime import UTC, datetime

from config.types import TaskType
from persistence.errors import PersistenceTransactionError
from task_queue import PendingDelivery, TaskMessage
from workflow.types import TransitionRequest, TransitionSignal, WorkflowState

from worker.fakes.handlers import RecordingHandler
from worker.fakes.task_queue import FakeTaskQueue
from worker.fakes.transaction import FakeTransactionManager
from worker.fakes.workflow_engine import FakeWorkflowEngine

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _delivery() -> PendingDelivery:
    return PendingDelivery(
        message=TaskMessage(
            task_id="task-1",
            workflow_id="wf-1",
            task_type=TaskType.COLLECT,
            attempt=1,
            created_at=_FIXED_NOW,
            payload_reference="ref://payload/1",
        ),
        stream="cartoon:tasks",
        consumer_group="workers",
        delivery_id="del-1",
        dequeued_at=_FIXED_NOW,
    )


def test_fake_task_queue_dequeue_and_ack_recording() -> None:
    queue = FakeTaskQueue()
    delivery = _delivery()
    queue.enqueue_delivery(delivery)
    dequeued = queue.dequeue("cartoon:tasks", "workers", "worker-1", block_ms=0)
    assert dequeued is delivery
    queue.ack(delivery)
    assert queue.acked == [delivery.delivery_id]


def test_fake_task_queue_redelivers_unacked_delivery() -> None:
    queue = FakeTaskQueue()
    delivery = _delivery()
    queue.enqueue_delivery(delivery)
    first = queue.dequeue("cartoon:tasks", "workers", "worker-1", block_ms=0)
    second = queue.dequeue("cartoon:tasks", "workers", "worker-1", block_ms=0)
    assert first is delivery
    assert second is delivery
    queue.ack(delivery)
    assert queue.dequeue("cartoon:tasks", "workers", "worker-1", block_ms=0) is None


def test_fake_transaction_manager_commit_probe() -> None:
    manager = FakeTransactionManager()
    assert not manager.is_in_transaction()
    with manager.transaction():
        assert manager.is_in_transaction()
    assert not manager.is_in_transaction()
    assert manager.commits == 1


def test_fake_transaction_manager_rejects_nested_transaction() -> None:
    manager = FakeTransactionManager()
    with manager.transaction():
        with pytest.raises(PersistenceTransactionError):
            with manager.transaction():
                pass


def test_fake_workflow_engine_records_transitions() -> None:
    engine = FakeWorkflowEngine()
    request = TransitionRequest(
        workflow_id="wf-1",
        expected_state=WorkflowState.COLLECTING,
        signal=TransitionSignal.STAGE_COMPLETED,
        reason="test",
        completing_task_id="task-1",
    )
    engine.apply_transition(request)
    assert engine.transitions == [request]


def test_recording_handler_increments_calls() -> None:
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    handler.handle(object())
    handler.handle(object())
    assert handler.calls == 2
