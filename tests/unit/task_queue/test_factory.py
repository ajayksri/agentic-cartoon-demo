"""Pre-code test mold for TQ-009 — TaskQueueFactory (LLD §3.7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.errors import ConfigCredentialMissingError
from task_queue import TaskQueue, TaskQueueConnectionError


def test_factory_create_returns_task_queue() -> None:
    """TaskQueueFactory.create returns a connected TaskQueue implementation."""
    from task_queue.factory import TaskQueueFactory
    from task_queue.redis_queue import RedisTaskQueue

    connection_manager = MagicMock()
    connection_manager.connect.return_value = MagicMock()
    factory = TaskQueueFactory(connection_manager=connection_manager)
    config = SimpleNamespace()

    queue = factory.create(config)  # type: ignore[arg-type]

    assert isinstance(queue, RedisTaskQueue)
    connection_manager.connect.assert_called_once()


def test_factory_default_boundary_logger_is_noop() -> None:
    """Default factory uses NoOpQueueBoundaryLogger."""
    from task_queue.boundary_log import NoOpQueueBoundaryLogger
    from task_queue.factory import TaskQueueFactory

    factory = TaskQueueFactory()

    assert isinstance(factory._boundary_logger, NoOpQueueBoundaryLogger)  # type: ignore[attr-defined]


def test_factory_injectable_connection_manager() -> None:
    """Injectable connection_manager enables unit tests without live Redis."""
    from task_queue.factory import TaskQueueFactory

    connection_manager = MagicMock()
    connection_manager.connect.return_value = MagicMock()
    factory = TaskQueueFactory(connection_manager=connection_manager)

    factory.create(SimpleNamespace())  # type: ignore[arg-type]

    connection_manager.connect.assert_called_once()


def test_factory_translates_config_credential_missing_error() -> None:
    """ConfigCredentialMissingError from credential resolve → TaskQueueConnectionError."""
    from unittest.mock import patch

    from task_queue.factory import TaskQueueFactory

    config = SimpleNamespace(
        infrastructure=SimpleNamespace(
            redis=SimpleNamespace(host="localhost", port=6379),
        ),
    )

    with patch(
        "task_queue.factory.RedisConnectionManager.from_app_config",
        side_effect=ConfigCredentialMissingError(
            "missing",
            env_var_name="REDIS_PASSWORD",
        ),
    ):
        factory = TaskQueueFactory()
        with pytest.raises(TaskQueueConnectionError) as exc_info:
            factory.create(config)  # type: ignore[arg-type]

    assert exc_info.value.code == "TQ_CONN"
    assert "REDIS_PASSWORD" not in str(exc_info.value)


def test_create_task_queue_public_entry_returns_task_queue() -> None:
    """Public create_task_queue returns TaskQueue protocol instance."""
    from task_queue import create_task_queue
    from task_queue.factory import TaskQueueFactory

    connection_manager = MagicMock()
    connection_manager.connect.return_value = MagicMock()
    factory = TaskQueueFactory(connection_manager=connection_manager)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "task_queue.factory._DEFAULT_FACTORY",
            factory,
        )
        queue = create_task_queue(SimpleNamespace())  # type: ignore[arg-type]

    assert isinstance(queue, TaskQueue)


def test_factory_wires_boundary_logger_to_stats_collector() -> None:
    """Default collaborator graph shares boundary_logger with QueueStatsCollector."""
    from task_queue.boundary_log import QueueBoundaryLogger
    from task_queue.factory import TaskQueueFactory

    logger = MagicMock(spec=QueueBoundaryLogger)
    connection_manager = MagicMock()
    connection_manager.connect.return_value = MagicMock()
    factory = TaskQueueFactory(
        boundary_logger=logger,
        connection_manager=connection_manager,
    )

    queue = factory.create(SimpleNamespace())  # type: ignore[arg-type]

    assert queue._boundary_logger is logger  # type: ignore[attr-defined]
    assert queue._stats_collector._boundary_logger is logger  # type: ignore[attr-defined]
