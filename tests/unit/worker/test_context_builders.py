"""Unit tests for WKR-007 context builders (LLD §4.7–§4.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.types import AgentRunContext
from config.types import AgentId, TaskType
from persistence.types import PayloadReference, TaskRecord, TaskStatus, TaskType as PersTaskType
from task_queue import PendingDelivery, TaskMessage

from worker.context import AgentRunContextBuilder, TaskExecutionContextBuilder
from worker.types import TaskTiming

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


def _task_record() -> TaskRecord:
    return TaskRecord(
        task_id="task-1",
        workflow_id="wf-1",
        task_type=PersTaskType.COLLECT,
        attempt=1,
        status=TaskStatus.DISPATCHED,
        payload_reference=PayloadReference(ref_id="pl-1", ref_kind="task_payload"),
        idempotency_key="idem-1",
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def test_task_execution_context_builder_assembles_frozen_context() -> None:
    delivery = _delivery()
    timing = TaskTiming(enqueued_at=_FIXED_NOW, dequeued_at=_FIXED_NOW)
    provider = SimpleNamespace(provider_id=AgentId.TOPIC_SELECTOR)
    context = TaskExecutionContextBuilder.build(
        worker_id="worker-1",
        config=SimpleNamespace(),
        delivery=delivery,
        task_record=_task_record(),
        idempotency_key="wf-1:COLLECT:1",
        timing=timing,
        workflow_engine=MagicMock(),
        workflow_repo=MagicMock(),
        artifact_repo=MagicMock(),
        idempotency_orchestrator=MagicMock(),
        transaction_manager=MagicMock(),
        failure_injection=MagicMock(),
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        collector=MagicMock(),
        topic_selection_agent=MagicMock(),
        scenario_generation_agent=MagicMock(),
        critic_agent=MagicMock(),
        model_provider_factory=lambda _aid: provider,
    )
    assert context.worker_id == "worker-1"
    assert context.delivery is delivery
    assert context.idempotency_key == "wf-1:COLLECT:1"
    with pytest.raises(AttributeError):
        context.worker_id = "other"  # type: ignore[misc]


def test_agent_run_context_builder_invokes_provider_factory() -> None:
    delivery = _delivery()
    provider = SimpleNamespace(provider_id=AgentId.CRITIC)
    factory = MagicMock(return_value=provider)
    context = AgentRunContextBuilder.build(
        agent_id=AgentId.CRITIC,
        delivery=delivery,
        config=SimpleNamespace(),
        model_provider_factory=factory,
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
        attempt=2,
    )
    factory.assert_called_once_with(AgentId.CRITIC)
    assert isinstance(context, AgentRunContext)
    assert context.workflow_id == "wf-1"
    assert context.task_id == "task-1"
    assert context.task_attempt == 2
    assert context.provider is provider
