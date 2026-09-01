"""Task handler registry (LLD §4.2)."""

from __future__ import annotations

from collections.abc import Sequence

from config.types import TaskType

from .errors import DuplicateHandlerError, HandlerNotFoundError
from .messages import handler_not_found_message
from .protocols import TaskHandler


class DefaultTaskHandlerRegistry:
    """Registry of TaskHandler instances keyed by TaskType."""

    def __init__(self) -> None:
        self._handlers: dict[TaskType, TaskHandler] = {}

    def register(self, handler: TaskHandler) -> None:
        task_type = handler.task_type
        if task_type in self._handlers:
            raise DuplicateHandlerError(
                f"Handler already registered for {task_type.value}",
                task_type=task_type,
            )
        self._handlers[task_type] = handler

    def get_handler(self, task_type: TaskType) -> TaskHandler:
        handler = self._handlers.get(task_type)
        if handler is None:
            raise HandlerNotFoundError(
                handler_not_found_message(task_type=task_type),
                task_type=task_type,
            )
        return handler

    def supported_task_types(self) -> frozenset[TaskType]:
        return frozenset(self._handlers.keys())


def create_task_handler_registry(
    *,
    handlers: Sequence[TaskHandler],
) -> DefaultTaskHandlerRegistry:
    registry = DefaultTaskHandlerRegistry()
    seen: set[TaskType] = set()
    for handler in handlers:
        task_type = handler.task_type
        if task_type in seen:
            raise DuplicateHandlerError(
                f"Duplicate handler for {task_type.value} in factory input",
                task_type=task_type,
            )
        seen.add(task_type)
        registry.register(handler)
    return registry
