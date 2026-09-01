"""Queue depth and oldest-message age computation (LLD §3.4)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

import redis

from .boundary_log import QueueBoundaryLogger, TaskQueueErrorEvent
from .conventions import STREAM_CONVENTIONS, StreamConvention, resolve_consumer_group
from .errors import ConsumerGroupError
from .messages import consumer_group_message
from .types import QueueStats
from .validation import MessageValidator


def _pending_count(summary: object) -> int:
    """Normalize XPENDING summary across redis-py 4 (tuple) and 5 (dict)."""
    if isinstance(summary, dict):
        return int(summary.get("pending", 0))
    return int(summary[0])


class QueueStatsCollector:
    def __init__(
        self,
        redis_client: redis.Redis,
        *,
        conventions: Mapping[str, StreamConvention] | None = None,
        clock: Callable[[], datetime] | None = None,
        boundary_logger: QueueBoundaryLogger | None = None,
    ) -> None:
        self._client = redis_client
        self._conventions = conventions or STREAM_CONVENTIONS
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._boundary_logger = boundary_logger
        self._validator = MessageValidator()

    def collect(self, stream: str) -> QueueStats:
        group = resolve_consumer_group(stream)
        groups = self._client.xinfo_groups(stream)
        row = self._find_group_row(groups, group, stream=stream)

        lag = int(row["lag"])
        pending_summary = self._client.xpending(stream, group)
        pending_count = _pending_count(pending_summary)
        depth = lag + pending_count

        if depth == 0:
            return QueueStats(depth=0, oldest_message_age_seconds=0.0)

        created_at_values: list[datetime] = []

        for delivery_id, _consumer in self._pending_entries(stream, group):
            created_at = self._created_at_for_entry(stream, delivery_id)
            if created_at is not None:
                created_at_values.append(created_at)

        for entry_id in self._lag_entry_ids(stream, group):
            created_at = self._created_at_for_entry(stream, entry_id)
            if created_at is not None:
                created_at_values.append(created_at)

        if not created_at_values:
            if self._boundary_logger is not None:
                self._boundary_logger.emit(
                    TaskQueueErrorEvent(
                        stream=stream,
                        error_code="TQ_INVALID_MESSAGE",
                        consumer_group=group,
                    )
                )
            return QueueStats(depth=depth, oldest_message_age_seconds=0.0)

        min_ts = min(created_at_values)
        now_utc = self._clock()
        age = max(0.0, (now_utc - min_ts).total_seconds())
        return QueueStats(depth=depth, oldest_message_age_seconds=age)

    def _find_group_row(
        self,
        groups: list[dict[str, Any]],
        group: str,
        *,
        stream: str | None = None,
    ) -> dict[str, Any]:
        for row in groups:
            if row.get("name") == group:
                return row

        stream_for_error = stream or self._stream_for_group(group)
        raise ConsumerGroupError(
            consumer_group_message(
                stream=stream_for_error,
                group=group,
                reason="consumer group not found",
            ),
            stream=stream_for_error,
            group=group,
        )

    def _pending_entries(self, stream: str, group: str) -> list[tuple[str, str]]:
        groups = self._client.xinfo_groups(stream)
        self._find_group_row(groups, group, stream=stream)
        pending_range = self._client.xpending_range(stream, group, "-", "+", count=1000)
        return [(entry["message_id"], entry["consumer"]) for entry in pending_range]

    def _lag_entry_ids(self, stream: str, group: str) -> list[str]:
        groups = self._client.xinfo_groups(stream)
        row = self._find_group_row(groups, group, stream=stream)
        last_delivered_id = row["last-delivered-id"]
        entries = self._client.xrange(stream, min=f"({last_delivered_id}", max="+")
        return [entry_id for entry_id, _fields in entries]

    def _created_at_for_entry(
        self,
        stream: str,
        entry_id: str,
    ) -> datetime | None:
        entries = self._client.xrange(stream, min=entry_id, max=entry_id, count=1)
        if not entries:
            return None

        _, fields = entries[0]
        created_at_raw = fields.get("created_at")
        if created_at_raw is None:
            return None

        if isinstance(created_at_raw, bytes):
            created_at_raw = created_at_raw.decode()

        return self._validator._parse_created_at(created_at_raw)  # noqa: SLF001

    def _stream_for_group(self, group: str) -> str:
        for stream, convention in self._conventions.items():
            if convention.consumer_group == group:
                return stream
        return group
