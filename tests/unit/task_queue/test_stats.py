"""Pre-code test mold for TQ-007 — QueueStatsCollector (LLD §3.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from task_queue import ConsumerGroupError, QueueStats


COLLECT_STREAM = "cartoon:tasks:collect"
COLLECT_GROUP = "cartoon:workers:collect"


def test_collect_zero_depth_returns_zeros() -> None:
    """depth == 0 returns QueueStats with oldest_message_age_seconds == 0.0 (TQ-TC-005)."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 0, "last-delivered-id": "0-0"},
    ]
    client.xpending.return_value = (0, None, None, None)
    collector = QueueStatsCollector(client)

    stats = collector.collect(COLLECT_STREAM)

    assert stats == QueueStats(depth=0, oldest_message_age_seconds=0.0)


def test_collect_depth_equals_lag_plus_pending_count() -> None:
    """depth = lag + pending_count per LLD depth algorithm."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 3, "last-delivered-id": "1000-0"},
    ]
    client.xpending.return_value = (2, "1001-0", "1002-0", None)
    client.xrange.return_value = []
    client.xpending_range.return_value = []
    fixed_now = datetime(2026, 8, 31, 12, 5, 0, tzinfo=timezone.utc)
    collector = QueueStatsCollector(client, clock=lambda: fixed_now)

    stats = collector.collect(COLLECT_STREAM)

    assert stats.depth == 5


def test_collect_depth_supports_redis_py5_xpending_dict() -> None:
    """redis-py 5 returns XPENDING summary as a dict."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 1, "last-delivered-id": "1000-0"},
    ]
    client.xpending.return_value = {
        "pending": 2,
        "min": "1001-0",
        "max": "1002-0",
        "consumers": [],
    }
    client.xrange.return_value = []
    client.xpending_range.return_value = []
    collector = QueueStatsCollector(client)

    stats = collector.collect(COLLECT_STREAM)

    assert stats.depth == 3


def test_collect_oldest_age_from_min_created_at() -> None:
    """oldest_message_age_seconds uses min(created_at) over depth contributors."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 1, "last-delivered-id": "1000-0"},
    ]
    client.xpending.return_value = (0, None, None, None)
    client.xrange.return_value = [
        (
            "1001-0",
            {
                "created_at": "2026-08-31T12:00:00.000000Z",
                "task_id": "task-1",
            },
        )
    ]
    fixed_now = datetime(2026, 8, 31, 12, 2, 30, tzinfo=timezone.utc)
    collector = QueueStatsCollector(client, clock=lambda: fixed_now)

    stats = collector.collect(COLLECT_STREAM)

    assert stats.depth >= 1
    assert stats.oldest_message_age_seconds == pytest.approx(150.0)


def test_find_group_row_raises_when_convention_group_absent() -> None:
    """Missing convention group row raises ConsumerGroupError."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    collector = QueueStatsCollector(client)

    with pytest.raises(ConsumerGroupError) as exc_info:
        collector._find_group_row(  # noqa: SLF001
            [{"name": "other-group"}],
            COLLECT_GROUP,
        )

    assert exc_info.value.stream == COLLECT_STREAM
    assert exc_info.value.group == COLLECT_GROUP


def test_lag_entry_ids_uses_exclusive_xrange() -> None:
    """_lag_entry_ids enumerates entries after last-delivered-id exclusively."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "last-delivered-id": "1000-0"},
    ]
    client.xrange.return_value = [("1002-0", {}), ("1003-0", {})]
    collector = QueueStatsCollector(client)

    entry_ids = collector._lag_entry_ids(COLLECT_STREAM, COLLECT_GROUP)  # noqa: SLF001

    client.xrange.assert_called_once_with(
        COLLECT_STREAM,
        min="(1000-0",
        max="+",
    )
    assert entry_ids == ["1002-0", "1003-0"]


def test_collect_oldest_age_includes_pending_entries() -> None:
    """oldest_message_age_seconds considers pending entries via min(created_at)."""
    from task_queue.stats import QueueStatsCollector

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 0, "last-delivered-id": "1000-0"},
    ]
    client.xpending.return_value = (1, "1001-0", "1001-0", None)
    client.xpending_range.return_value = [
        {"message_id": "1001-0", "consumer": "worker-1"},
    ]
    client.xrange.return_value = [
        (
            "1001-0",
            {
                "created_at": "2026-08-31T11:58:00.000000Z",
                "task_id": "task-1",
            },
        )
    ]
    fixed_now = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    collector = QueueStatsCollector(client, clock=lambda: fixed_now)

    stats = collector.collect(COLLECT_STREAM)

    assert stats.depth == 1
    assert stats.oldest_message_age_seconds == pytest.approx(120.0)


def test_corrupt_created_at_emits_boundary_event_and_returns_zero_age() -> None:
    """Degenerate corrupt-entry path emits TaskQueueErrorEvent and returns 0.0 age."""
    from task_queue.boundary_log import TaskQueueErrorEvent
    from task_queue.stats import QueueStatsCollector

    logger = MagicMock()
    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": COLLECT_GROUP, "lag": 1, "last-delivered-id": "1000-0"},
    ]
    client.xpending.return_value = (0, None, None, None)
    client.xrange.return_value = [("1001-0", {"created_at": "not-valid"})]
    collector = QueueStatsCollector(client, boundary_logger=logger)

    stats = collector.collect(COLLECT_STREAM)

    assert stats.oldest_message_age_seconds == 0.0
    logger.emit.assert_called()
    event = logger.emit.call_args.args[0]
    assert isinstance(event, TaskQueueErrorEvent)
    assert event.error_code == "TQ_INVALID_MESSAGE"
