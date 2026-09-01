"""Shared contract-test helpers for task_queue module (TQ-010, LLD §9.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from config.types import TaskType
from task_queue import TaskMessage

COLLECT_STREAM = "cartoon:tasks:collect"
COLLECT_GROUP = "cartoon:workers:collect"


def minimal_task_message(**overrides: object) -> TaskMessage:
    """Valid TaskMessage factory for contract tests."""
    defaults: dict[str, object] = {
        "task_id": "task-contract-1",
        "workflow_id": "wf-contract-1",
        "task_type": TaskType.COLLECT,
        "attempt": 1,
        "created_at": datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc),
        "payload_reference": "ref://payload/contract-1",
    }
    defaults.update(overrides)
    return TaskMessage(**defaults)  # type: ignore[arg-type]
