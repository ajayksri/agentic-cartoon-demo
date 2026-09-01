"""Redis Streams TaskQueue implementation (LLD §3.6, §5)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: At-least-once task transport — Redis Streams with
# consumer groups deliver tasks reliably; ACK-after-commit makes duplicates expected.

from __future__ import annotations

from datetime import datetime, timezone

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError

from .boundary_log import (
    NoOpQueueBoundaryLogger,
    QueueBoundaryLogger,
    TaskAckedEvent,
    TaskDequeuedEvent,
    TaskEnqueuedEvent,
    TaskQueueErrorEvent,
)
from .connection import RedisConnectionManager
from .consumer_groups import ConsumerGroupManager
from .errors import (
    AckError,
    ConsumerGroupError,
    InvalidTaskMessageError,
    StreamNotFoundError,
    TaskQueueConnectionError,
    TaskQueueError,
    TaskQueueUnavailableError,
)
from .messages import (
    ack_message,
    consumer_group_message,
    connection_message,
    invalid_message_message,
    stream_not_found_message,
    unavailable_message,
)
from .serializer import MessageSerializer
from .stats import QueueStatsCollector
from .types import EnqueueResult, PendingDelivery, QueueStats, TaskMessage
from .validation import MessageValidator
from .conventions import resolve_consumer_group

DEFAULT_BLOCK_MS = 5000


class RedisTaskQueue:
    def __init__(
        self,
        *,
        connection: RedisConnectionManager,
        serializer: MessageSerializer | None = None,
        validator: MessageValidator | None = None,
        group_manager: ConsumerGroupManager | None = None,
        stats_collector: QueueStatsCollector | None = None,
        boundary_logger: QueueBoundaryLogger | None = None,
        block_ms_default: int = DEFAULT_BLOCK_MS,
    ) -> None:
        self._connection = connection
        self._validator = validator or MessageValidator()
        self._serializer = serializer or MessageSerializer(self._validator)
        self._boundary_logger = boundary_logger or NoOpQueueBoundaryLogger()
        self._block_ms_default = block_ms_default

        client = connection.client()
        self._group_manager = group_manager or ConsumerGroupManager(client)
        self._stats_collector = stats_collector or QueueStatsCollector(
            client,
            boundary_logger=self._boundary_logger,
        )

    def enqueue(self, stream: str, message: TaskMessage) -> EnqueueResult:
        self._validate_stream_for_enqueue(stream)
        try:
            self._validator.validate(message)
        except InvalidTaskMessageError as exc:
            raise exc

        fields = self._serializer.encode(message)
        client = self._connection.client()
        try:
            delivery_id = client.xadd(stream, fields)
        except (RedisTimeoutError, TimeoutError) as exc:
            raise TaskQueueUnavailableError(
                unavailable_message(operation="enqueue", reason=str(exc)),
            ) from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise self._connection_error(exc) from exc

        self._boundary_logger.emit(
            TaskEnqueuedEvent(
                workflow_id=message.workflow_id,
                task_id=message.task_id,
                task_type=message.task_type,
                stream=stream,
                delivery_id=delivery_id,
            )
        )
        return EnqueueResult(
            delivery_id=delivery_id,
            enqueued_at=datetime.now(timezone.utc),
        )

    def dequeue(
        self,
        stream: str,
        *,
        consumer_group: str,
        consumer_name: str,
        block_ms: int | None = None,
    ) -> PendingDelivery | None:
        self._validate_stream_for_dequeue(stream, consumer_group, consumer_name)

        resolved_block_ms = self._resolve_block_ms(block_ms)

        if not self._group_manager.group_exists(stream, consumer_group):
            raise ConsumerGroupError(
                consumer_group_message(
                    stream=stream,
                    group=consumer_group,
                    reason="consumer group does not exist",
                ),
                stream=stream,
                group=consumer_group,
            )

        client = self._connection.client()
        read_kwargs: dict[str, int] = {"count": 1}
        if resolved_block_ms > 0:
            read_kwargs["block"] = resolved_block_ms

        try:
            response = client.xreadgroup(
                consumer_group,
                consumer_name,
                {stream: ">"},
                **read_kwargs,
            )
        except (RedisTimeoutError, TimeoutError) as exc:
            raise TaskQueueUnavailableError(
                unavailable_message(operation="dequeue", reason=str(exc)),
            ) from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise self._connection_error(exc) from exc

        if not response:
            response = self._claim_pending_delivery(
                client,
                stream,
                consumer_group,
                consumer_name,
            )

        if not response:
            return None

        _stream_name, entries = response[0]
        delivery_id, field_map = entries[0]

        if isinstance(delivery_id, bytes):
            delivery_id = delivery_id.decode()

        try:
            message = self._serializer.decode(field_map)
        except InvalidTaskMessageError as exc:
            try:
                client.xack(stream, consumer_group, delivery_id)
            except (RedisConnectionError, RedisError, OSError):
                pass
            self._boundary_logger.emit(
                TaskQueueErrorEvent(
                    stream=stream,
                    error_code=exc.code,
                    consumer_group=consumer_group,
                    delivery_id=delivery_id,
                )
            )
            raise InvalidTaskMessageError(
                invalid_message_message(
                    stream=stream,
                    delivery_id=delivery_id,
                    missing_fields=exc.missing_fields,
                ),
                missing_fields=exc.missing_fields,
            ) from exc

        self._boundary_logger.emit(
            TaskDequeuedEvent(
                workflow_id=message.workflow_id,
                task_id=message.task_id,
                task_type=message.task_type,
                stream=stream,
                consumer_group=consumer_group,
                delivery_id=delivery_id,
            )
        )
        return PendingDelivery(
            message=message,
            stream=stream,
            consumer_group=consumer_group,
            delivery_id=delivery_id,
            dequeued_at=datetime.now(timezone.utc),
        )

    def ack(self, delivery: PendingDelivery) -> None:
        client = self._connection.client()
        try:
            count = client.xack(
                delivery.stream,
                delivery.consumer_group,
                delivery.delivery_id,
            )
        except (RedisTimeoutError, TimeoutError) as exc:
            raise TaskQueueUnavailableError(
                unavailable_message(operation="ack", reason=str(exc)),
            ) from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise self._connection_error(exc) from exc

        if count == 0:
            raise AckError(
                ack_message(
                    delivery_id=delivery.delivery_id,
                    reason="delivery not found or already acknowledged",
                ),
                delivery_id=delivery.delivery_id,
            )

        self._boundary_logger.emit(
            TaskAckedEvent(
                workflow_id=delivery.message.workflow_id,
                task_id=delivery.message.task_id,
                task_type=delivery.message.task_type,
                stream=delivery.stream,
                consumer_group=delivery.consumer_group,
                delivery_id=delivery.delivery_id,
            )
        )

    def ensure_consumer_group(
        self,
        stream: str,
        group: str,
        *,
        start_id: str = "0",
    ) -> None:
        self._validate_stream_for_dequeue(stream, group, "consumer")
        try:
            self._group_manager.ensure_group(stream, group, start_id=start_id)
        except ConsumerGroupError as exc:
            self._emit_error(exc, stream=stream, consumer_group=group)
            raise

    def get_queue_stats(self, stream: str) -> QueueStats:
        try:
            group = resolve_consumer_group(stream)
        except StreamNotFoundError as exc:
            self._emit_error(exc, stream=stream)
            raise

        if not self._is_valid_stream_name(stream):
            exc = StreamNotFoundError(
                stream_not_found_message(stream=stream),
                stream=stream,
            )
            self._emit_error(exc, stream=stream)
            raise exc

        client = self._connection.client()
        try:
            if not client.exists(stream):
                exc = StreamNotFoundError(
                    stream_not_found_message(stream=stream),
                    stream=stream,
                )
                self._emit_error(exc, stream=stream)
                raise exc
        except (RedisTimeoutError, TimeoutError) as exc:
            unavailable = TaskQueueUnavailableError(
                unavailable_message(operation="get_queue_stats", reason=str(exc)),
            )
            self._emit_error(unavailable, stream=stream, consumer_group=group)
            raise unavailable from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            conn_err = self._connection_error(exc)
            self._emit_error(conn_err, stream=stream, consumer_group=group)
            raise conn_err from exc

        try:
            return self._stats_collector.collect(stream)
        except ConsumerGroupError as exc:
            self._emit_error(exc, stream=stream, consumer_group=group)
            raise
        except (RedisTimeoutError, TimeoutError) as exc:
            unavailable = TaskQueueUnavailableError(
                unavailable_message(operation="get_queue_stats", reason=str(exc)),
            )
            self._emit_error(unavailable, stream=stream, consumer_group=group)
            raise unavailable from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            conn_err = self._connection_error(exc)
            self._emit_error(conn_err, stream=stream, consumer_group=group)
            raise conn_err from exc

    def close(self) -> None:
        self._connection.close()

    def _resolve_block_ms(self, block_ms: int | None) -> int:
        if block_ms is None:
            return self._block_ms_default
        if block_ms <= 0:
            return 0
        return block_ms

    def _claim_pending_delivery(
        self,
        client: redis.Redis,
        stream: str,
        consumer_group: str,
        consumer_name: str,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]] | None:
        """Reclaim unacked pending entries via XAUTOCLAIM (at-least-once redelivery)."""
        try:
            _next_start, messages, _deleted = client.xautoclaim(
                stream,
                consumer_group,
                consumer_name,
                0,
                "0-0",
                count=1,
            )
        except (RedisTimeoutError, TimeoutError) as exc:
            raise TaskQueueUnavailableError(
                unavailable_message(operation="dequeue", reason=str(exc)),
            ) from exc
        except (RedisConnectionError, RedisError, OSError) as exc:
            raise self._connection_error(exc) from exc

        if not messages:
            return None
        return [(stream, messages)]

    def _validate_stream_for_enqueue(self, stream: str) -> None:
        if not self._is_valid_stream_name(stream):
            raise StreamNotFoundError(
                stream_not_found_message(stream=stream),
                stream=stream,
            )

    def _validate_stream_for_dequeue(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
    ) -> None:
        if not self._is_valid_stream_name(stream):
            raise ConsumerGroupError(
                consumer_group_message(
                    stream=stream,
                    group=consumer_group,
                    reason="invalid stream name",
                ),
                stream=stream,
                group=consumer_group,
            )
        if not consumer_group.strip():
            raise ConsumerGroupError(
                consumer_group_message(
                    stream=stream,
                    group=consumer_group,
                    reason="invalid consumer group",
                ),
                stream=stream,
                group=consumer_group,
            )
        if not consumer_name.strip():
            raise ConsumerGroupError(
                consumer_group_message(
                    stream=stream,
                    group=consumer_group,
                    reason="invalid consumer name",
                ),
                stream=stream,
                group=consumer_group,
            )

    def _is_valid_stream_name(self, stream: str) -> bool:
        stripped = stream.strip()
        if not stripped:
            return False
        return not any(char.isspace() for char in stripped)

    def _connection_error(self, exc: BaseException) -> TaskQueueConnectionError:
        params = self._connection._params  # noqa: SLF001
        return TaskQueueConnectionError(
            connection_message(
                host=params.host,
                port=params.port,
                reason=str(exc),
            ),
        )

    def _emit_error(
        self,
        exc: TaskQueueError,
        *,
        stream: str,
        consumer_group: str | None = None,
        delivery_id: str | None = None,
    ) -> None:
        self._boundary_logger.emit(
            TaskQueueErrorEvent(
                stream=stream,
                error_code=exc.code,
                consumer_group=consumer_group,
                delivery_id=delivery_id,
            )
        )
