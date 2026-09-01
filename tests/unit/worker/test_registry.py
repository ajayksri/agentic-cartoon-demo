"""Unit tests for WKR-009 task handler registry (LLD §4.2)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from worker.errors import DuplicateHandlerError, HandlerNotFoundError
from worker.fakes.handlers import RecordingHandler
from worker.registry import create_task_handler_registry


def test_register_and_lookup_handler() -> None:
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    registry = create_task_handler_registry(handlers=[handler])
    resolved = registry.get_handler(TaskType.COLLECT)
    assert resolved is handler
    assert registry.supported_task_types() == frozenset({TaskType.COLLECT})


def test_duplicate_registration_raises() -> None:
    handlers = [
        RecordingHandler(_task_type=TaskType.COLLECT),
        RecordingHandler(_task_type=TaskType.COLLECT),
    ]
    with pytest.raises(DuplicateHandlerError):
        create_task_handler_registry(handlers=handlers)


def test_missing_handler_raises() -> None:
    registry = create_task_handler_registry(handlers=[])
    with pytest.raises(HandlerNotFoundError) as exc_info:
        registry.get_handler(TaskType.SELECT_TOPIC)
    assert exc_info.value.task_type == TaskType.SELECT_TOPIC
