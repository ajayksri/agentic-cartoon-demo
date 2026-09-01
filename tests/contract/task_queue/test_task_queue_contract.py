"""Contract tests TQ-TC-001 through TQ-TC-015 (TQ-010).

Imports ONLY from the task_queue package public surface.
"""

from __future__ import annotations

import inspect
import typing

import pytest

from .fake_queue import InMemoryTaskQueue
from .helpers import COLLECT_GROUP, COLLECT_STREAM, minimal_task_message
from task_queue import (
    AckError,
    ConsumerGroupError,
    InvalidTaskMessageError,
    QueueStats,
    TaskQueue,
    TaskQueueConnectionError,
    TRACE_CARRIER_KEY_TRACEPARENT,
    TRACE_CARRIER_KEY_TRACESTATE,
    create_task_queue,
)


@pytest.mark.tq_tc("001")
def test_tq_tc_001_public_protocol_hides_redis() -> None:
    """TQ-TC-001: Public TaskQueue protocol hides Redis-specific types."""
    assert typing.runtime_checkable(TaskQueue)
    for name in ("enqueue", "dequeue", "ack", "ensure_consumer_group", "get_queue_stats"):
        assert hasattr(TaskQueue, name)

    sig = inspect.signature(TaskQueue.enqueue)
    for parameter in sig.parameters.values():
        assert "redis" not in str(parameter.annotation).lower()

    for exc_type in (
        TaskQueueConnectionError,
        InvalidTaskMessageError,
        ConsumerGroupError,
        AckError,
    ):
        assert "redis" not in exc_type.__name__.lower()

    queue = InMemoryTaskQueue()
    assert isinstance(queue, TaskQueue)
    queue.enqueue(COLLECT_STREAM, minimal_task_message())


@pytest.mark.tq_tc("002")
def test_tq_tc_002_factory_consumes_config_only(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-002: create_task_queue(AppConfig) returns TaskQueue without file paths."""
    assert isinstance(task_queue_instance, TaskQueue)


@pytest.mark.tq_tc("003")
def test_tq_tc_003_unacked_message_redeliverable(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-003: Message dequeued but not acked becomes available again."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message())

    first = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )
    assert first is not None

    second = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-2",
        block_ms=0,
    )

    assert second is not None
    assert second.delivery_id == first.delivery_id


@pytest.mark.tq_tc("004")
def test_tq_tc_004_ack_removes_pending_entry(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-004: ACK removes delivery from subsequent dequeue for the group."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message())

    delivery = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )
    assert delivery is not None
    task_queue_instance.ack(delivery)

    redelivered = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )

    assert redelivered is None


@pytest.mark.tq_tc("004b")
def test_tq_tc_004b_duplicate_ack_raises_ack_error(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-004b: Duplicate ACK raises AckError with code TQ_ACK."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message())

    delivery = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )
    assert delivery is not None
    task_queue_instance.ack(delivery)

    with pytest.raises(AckError) as exc_info:
        task_queue_instance.ack(delivery)

    assert exc_info.value.code == "TQ_ACK"


@pytest.mark.tq_tc("005")
def test_tq_tc_005_empty_queue_stats(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-005: Empty stream returns depth 0 and age 0.0."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)

    stats = task_queue_instance.get_queue_stats(COLLECT_STREAM)

    assert stats == QueueStats(depth=0, oldest_message_age_seconds=0.0)


@pytest.mark.tq_tc("006")
def test_tq_tc_006_nonempty_queue_exposes_depth_and_age(
    task_queue_instance: TaskQueue,
) -> None:
    """TQ-TC-006: Enqueued message yields depth >= 1 and age > 0."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message())

    stats = task_queue_instance.get_queue_stats(COLLECT_STREAM)

    assert stats.depth >= 1
    assert stats.oldest_message_age_seconds > 0.0


@pytest.mark.tq_tc("007")
def test_tq_tc_007_messages_accumulate_under_producer_overrun(
    task_queue_instance: TaskQueue,
) -> None:
    """TQ-TC-007: depth increases when producer enqueues without dequeue."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)

    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-1"))
    first_stats = task_queue_instance.get_queue_stats(COLLECT_STREAM)

    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-2"))
    second_stats = task_queue_instance.get_queue_stats(COLLECT_STREAM)

    assert second_stats.depth > first_stats.depth


@pytest.mark.tq_tc("008")
def test_tq_tc_008_concurrency_not_enforced_by_queue() -> None:
    """TQ-TC-008: Queue returns messages without worker-side throttling."""
    queue = InMemoryTaskQueue()
    seed_consumer_group(queue, COLLECT_STREAM, COLLECT_GROUP)
    queue.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-1"))
    queue.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-2"))

    first = queue.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )
    second = queue.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-2",
        block_ms=0,
    )

    assert first is not None
    assert second is not None


@pytest.mark.tq_tc("009")
def test_tq_tc_009_valid_minimal_envelope_round_trip() -> None:
    """TQ-TC-009: enqueue then dequeue returns equivalent TaskMessage fields."""
    queue = InMemoryTaskQueue()
    seed_consumer_group(queue, COLLECT_STREAM, COLLECT_GROUP)
    message = minimal_task_message()

    queue.enqueue(COLLECT_STREAM, message)
    delivery = queue.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )

    assert delivery is not None
    assert delivery.message == message


@pytest.mark.tq_tc("010")
def test_tq_tc_010_missing_required_field_rejected_at_dequeue() -> None:
    """TQ-TC-010: Corrupt entry missing workflow_id raises InvalidTaskMessageError."""
    queue = InMemoryTaskQueue()
    seed_consumer_group(queue, COLLECT_STREAM, COLLECT_GROUP)

    with pytest.raises(InvalidTaskMessageError) as exc_info:
        queue.dequeue_corrupt_entry_for_test(  # type: ignore[attr-defined]
            COLLECT_STREAM,
            consumer_group=COLLECT_GROUP,
            consumer_name="worker-1",
            missing_field="workflow_id",
        )

    assert "workflow_id" in exc_info.value.missing_fields


@pytest.mark.tq_tc("011")
def test_tq_tc_011_invalid_attempt_rejected_on_enqueue() -> None:
    """TQ-TC-011: attempt=0 on enqueue raises InvalidTaskMessageError."""
    queue = InMemoryTaskQueue()
    seed_consumer_group(queue, COLLECT_STREAM, COLLECT_GROUP)

    with pytest.raises(InvalidTaskMessageError):
        queue.enqueue(COLLECT_STREAM, minimal_task_message(attempt=0))


@pytest.mark.tq_tc("012")
def test_tq_tc_012_trace_carrier_round_trip() -> None:
    """TQ-TC-012: traceparent preserved across enqueue/dequeue."""
    queue = InMemoryTaskQueue()
    seed_consumer_group(queue, COLLECT_STREAM, COLLECT_GROUP)
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    message = minimal_task_message(
        trace_carrier={
            TRACE_CARRIER_KEY_TRACEPARENT: traceparent,
            TRACE_CARRIER_KEY_TRACESTATE: "vendor=value",
        }
    )

    queue.enqueue(COLLECT_STREAM, message)
    delivery = queue.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )

    assert delivery is not None
    assert delivery.message.trace_carrier[TRACE_CARRIER_KEY_TRACEPARENT] == traceparent
    assert delivery.message.trace_carrier[TRACE_CARRIER_KEY_TRACESTATE] == "vendor=value"


@pytest.mark.tq_tc("013")
def test_tq_tc_013_ensure_consumer_group_idempotent(task_queue_instance: TaskQueue) -> None:
    """TQ-TC-013: ensure_consumer_group called twice succeeds without error."""
    task_queue_instance.ensure_consumer_group(COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.ensure_consumer_group(COLLECT_STREAM, COLLECT_GROUP)


@pytest.mark.tq_tc("014")
def test_tq_tc_014_competing_consumers_receive_distinct_deliveries(
    task_queue_instance: TaskQueue,
) -> None:
    """TQ-TC-014: Two consumers in same group receive distinct delivery_id values."""
    seed_consumer_group(task_queue_instance, COLLECT_STREAM, COLLECT_GROUP)
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-1"))
    task_queue_instance.enqueue(COLLECT_STREAM, minimal_task_message(task_id="task-2"))

    first = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-1",
        block_ms=0,
    )
    second = task_queue_instance.dequeue(
        COLLECT_STREAM,
        consumer_group=COLLECT_GROUP,
        consumer_name="worker-2",
        block_ms=0,
    )

    assert first is not None
    assert second is not None
    assert first.delivery_id != second.delivery_id


@pytest.mark.tq_tc("015")
def test_tq_tc_015_errors_omit_secrets_and_payloads() -> None:
    """TQ-TC-015: Connection errors omit password, API keys, and payload body."""
    from config.types import InfrastructureConfig, RedisConfig

    secret = "super-secret-redis-password"
    config = type(
        "TestAppConfig",
        (),
        {
            "infrastructure": InfrastructureConfig(
                postgres=type("Pg", (), {})(),  # type: ignore[arg-type]
                redis=RedisConfig(
                    host="127.0.0.1",
                    port=6399,
                    db=0,
                    password_env="REDIS_PASSWORD",
                ),
            ),
            "resolve_credential": lambda self, env_var_name: secret,
        },
    )()

    with pytest.raises(TaskQueueConnectionError) as exc_info:
        create_task_queue(config)  # type: ignore[arg-type]

    message = str(exc_info.value)
    assert secret not in message
    assert "ref://payload" not in message


def seed_consumer_group(queue: TaskQueue, stream: str, group: str) -> None:
    """Local wrapper to keep contract module imports public-only."""
    queue.ensure_consumer_group(stream, group)
