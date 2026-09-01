"""TaskQueue factory and public bootstrap (LLD §3.7)."""

from __future__ import annotations

from config.errors import ConfigCredentialMissingError
from config.types import AppConfig

from .boundary_log import NoOpQueueBoundaryLogger, QueueBoundaryLogger
from .connection import RedisConnectionManager
from .errors import TaskQueueConnectionError
from .messages import connection_message
from .protocols import TaskQueue
from .redis_queue import RedisTaskQueue

# Production runtime MUST use TaskQueueFactory(boundary_logger=adapter) per §3.7;
# public create_task_queue retains NoOp default.


class TaskQueueFactory:
    def __init__(
        self,
        *,
        boundary_logger: QueueBoundaryLogger | None = None,
        connection_manager: RedisConnectionManager | None = None,
    ) -> None:
        """connection_manager injected for tests; production builds from AppConfig."""
        self._boundary_logger = boundary_logger or NoOpQueueBoundaryLogger()
        self._connection_manager = connection_manager

    def create(self, config: AppConfig) -> RedisTaskQueue:
        """Build connection manager, connect, and return wired RedisTaskQueue."""
        try:
            if self._connection_manager is not None:
                manager = self._connection_manager
            else:
                manager = RedisConnectionManager.from_app_config(config)
        except ConfigCredentialMissingError as exc:
            redis_cfg = config.infrastructure.redis
            raise TaskQueueConnectionError(
                connection_message(
                    host=redis_cfg.host,
                    port=redis_cfg.port,
                    reason="credential resolution failed",
                ),
            ) from exc

        manager.connect()
        return RedisTaskQueue(
            connection=manager,
            boundary_logger=self._boundary_logger,
        )


_DEFAULT_FACTORY = TaskQueueFactory(boundary_logger=NoOpQueueBoundaryLogger())


def create_task_queue(config: AppConfig) -> TaskQueue:
    return _DEFAULT_FACTORY.create(config)
