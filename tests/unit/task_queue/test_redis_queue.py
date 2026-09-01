"""Pre-code test mold for TQ-008 — RedisTaskQueue (LLD §3.6, §5)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from config.types import TaskType
from task_queue import (
    AckError,
    ConsumerGroupError,
    InvalidTaskMessageError,
    PendingDelivery,
    StreamNotFoundError,
    TaskMessage,
)


def _valid_message(**overrides: object) -> TaskMessage:
    defaults: dict[str, object] = {
        "task_id": "task-1",
        "workflow_id": "wf-1",
        "task_type": TaskType.COLLECT,
        "attempt": 1,
        "created_at": datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc),
        "payload_reference": "ref://payload/1",
    }
    defaults.update(overrides)
    return TaskMessage(**defaults)  # type: ignore[arg-type]


def _pending_delivery() -> PendingDelivery:
    return PendingDelivery(
        message=_valid_message(),
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        delivery_id="1000-0",
        dequeued_at=datetime(2026, 8, 31, 12, 1, 0, tzinfo=timezone.utc),
    )


def test_enqueue_validation_failure_raises_invalid_task_message_error() -> None:
    """enqueue validates message before XADD."""
    from task_queue.redis_queue import RedisTaskQueue

    connection = MagicMock()
    queue = RedisTaskQueue(connection=connection)
    invalid = _valid_message(attempt=0)

    with pytest.raises(InvalidTaskMessageError):
        queue.enqueue("cartoon:tasks:collect", invalid)


def test_enqueue_calls_xadd_after_validation() -> None:
    """Successful enqueue encodes fields and calls XADD."""
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.xadd.return_value = "1000-0"
    connection = MagicMock()
    connection.client.return_value = client
    queue = RedisTaskQueue(connection=connection)

    result = queue.enqueue("cartoon:tasks:collect", _valid_message())

    client.xadd.assert_called_once()
    assert result.delivery_id == "1000-0"


def test_dequeue_without_consumer_group_raises_consumer_group_error() -> None:
    """dequeue without existing group raises ConsumerGroupError (MOD-TQ-INV-020)."""
    from task_queue.redis_queue import RedisTaskQueue

    group_manager = MagicMock()
    group_manager.group_exists.return_value = False
    connection = MagicMock()
    queue = RedisTaskQueue(connection=connection, group_manager=group_manager)

    with pytest.raises(ConsumerGroupError):
        queue.dequeue(
            "cartoon:tasks:collect",
            consumer_group="cartoon:workers:collect",
            consumer_name="worker-1",
        )


def test_dequeue_poison_ack_on_invalid_message() -> None:
    """Invalid envelope after XREADGROUP triggers best-effort poison ACK."""
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.xreadgroup.return_value = [
        [
            b"cartoon:tasks:collect",
            [(b"1000-0", {b"task_id": b"task-1"})],
        ]
    ]
    connection = MagicMock()
    connection.client.return_value = client
    group_manager = MagicMock()
    group_manager.group_exists.return_value = True
    queue = RedisTaskQueue(connection=connection, group_manager=group_manager)

    with pytest.raises(InvalidTaskMessageError):
        queue.dequeue(
            "cartoon:tasks:collect",
            consumer_group="cartoon:workers:collect",
            consumer_name="worker-1",
            block_ms=0,
        )

    client.xack.assert_called_once_with(
        "cartoon:tasks:collect",
        "cartoon:workers:collect",
        "1000-0",
    )


def test_ack_zero_count_raises_ack_error() -> None:
    """XACK returning 0 raises AckError with code TQ_ACK (TQ-TC-004b seam)."""
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.xack.return_value = 0
    connection = MagicMock()
    connection.client.return_value = client
    queue = RedisTaskQueue(connection=connection)

    with pytest.raises(AckError) as exc_info:
        queue.ack(_pending_delivery())

    assert exc_info.value.code == "TQ_ACK"
    assert exc_info.value.delivery_id == "1000-0"


def test_enqueue_empty_stream_raises_stream_not_found_error() -> None:
    """Invalid empty stream on enqueue raises StreamNotFoundError (LLD §4.3)."""
    from task_queue.redis_queue import RedisTaskQueue

    connection = MagicMock()
    queue = RedisTaskQueue(connection=connection)

    with pytest.raises(StreamNotFoundError):
        queue.enqueue("   ", _valid_message())


def test_dequeue_invalid_group_raises_consumer_group_error() -> None:
    """Invalid consumer_group on dequeue raises ConsumerGroupError."""
    from task_queue.redis_queue import RedisTaskQueue

    connection = MagicMock()
    queue = RedisTaskQueue(connection=connection)

    with pytest.raises(ConsumerGroupError):
        queue.dequeue(
            "cartoon:tasks:collect",
            consumer_group="  ",
            consumer_name="worker-1",
        )


def test_block_ms_none_uses_default() -> None:
    """block_ms=None resolves to default 5000 ms."""
    from task_queue.redis_queue import DEFAULT_BLOCK_MS, RedisTaskQueue

    client = MagicMock()
    client.xreadgroup.return_value = []
    client.xautoclaim.return_value = ("0-0", [], [])
    connection = MagicMock()
    connection.client.return_value = client
    group_manager = MagicMock()
    group_manager.group_exists.return_value = True
    queue = RedisTaskQueue(connection=connection, group_manager=group_manager)

    queue.dequeue(
        "cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        consumer_name="worker-1",
        block_ms=None,
    )

    assert client.xreadgroup.call_args.kwargs["block"] == DEFAULT_BLOCK_MS


def test_block_ms_zero_is_non_blocking() -> None:
    """block_ms <= 0 omits Redis BLOCK (BLOCK 0 means block forever in Redis)."""
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.xreadgroup.return_value = []
    client.xautoclaim.return_value = ("0-0", [], [])
    connection = MagicMock()
    connection.client.return_value = client
    group_manager = MagicMock()
    group_manager.group_exists.return_value = True
    queue = RedisTaskQueue(connection=connection, group_manager=group_manager)

    queue.dequeue(
        "cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        consumer_name="worker-1",
        block_ms=0,
    )

    assert "block" not in client.xreadgroup.call_args.kwargs


def test_get_queue_stats_raises_when_stream_missing() -> None:
    """get_queue_stats raises StreamNotFoundError when Redis EXISTS returns 0."""
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.exists.return_value = 0
    connection = MagicMock()
    connection.client.return_value = client
    boundary_logger = MagicMock()
    queue = RedisTaskQueue(connection=connection, boundary_logger=boundary_logger)

    with pytest.raises(StreamNotFoundError):
        queue.get_queue_stats("cartoon:tasks:collect")

    client.exists.assert_called_once_with("cartoon:tasks:collect")


def test_get_queue_stats_emits_boundary_event_on_stream_not_found() -> None:
    """get_queue_stats emits TaskQueueErrorEvent before StreamNotFoundError."""
    from task_queue.boundary_log import TaskQueueErrorEvent
    from task_queue.redis_queue import RedisTaskQueue

    client = MagicMock()
    client.exists.return_value = 0
    connection = MagicMock()
    connection.client.return_value = client
    boundary_logger = MagicMock()
    queue = RedisTaskQueue(connection=connection, boundary_logger=boundary_logger)

    with pytest.raises(StreamNotFoundError):
        queue.get_queue_stats("cartoon:tasks:collect")

    boundary_logger.emit.assert_called()
    event = boundary_logger.emit.call_args.args[0]
    assert isinstance(event, TaskQueueErrorEvent)
    assert event.error_code == "TQ_STREAM"
