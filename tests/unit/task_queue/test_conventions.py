"""Unit tests for TQ-002 — stream conventions (LLD §2.2)."""

from __future__ import annotations

import pytest

from config.types import TaskType
from task_queue import StreamNotFoundError
from task_queue.conventions import (
    STREAM_CONVENTIONS,
    resolve_consumer_group,
)


@pytest.mark.parametrize(
    ("stream", "consumer_group", "task_type"),
    [
        (
            "cartoon:tasks:collect",
            "cartoon:workers:collect",
            TaskType.COLLECT,
        ),
        (
            "cartoon:tasks:select_topic",
            "cartoon:workers:select_topic",
            TaskType.SELECT_TOPIC,
        ),
        (
            "cartoon:tasks:generate_scenario",
            "cartoon:workers:generate_scenario",
            TaskType.GENERATE_SCENARIO,
        ),
        (
            "cartoon:tasks:review_scenario",
            "cartoon:workers:review_scenario",
            TaskType.REVIEW_SCENARIO,
        ),
    ],
)
def test_stream_conventions_table(
    stream: str,
    consumer_group: str,
    task_type: TaskType,
) -> None:
    convention = STREAM_CONVENTIONS[stream]
    assert convention.stream == stream
    assert convention.consumer_group == consumer_group
    assert convention.task_type == task_type


def test_stream_conventions_has_exactly_four_entries() -> None:
    assert len(STREAM_CONVENTIONS) == 4


@pytest.mark.parametrize(
    ("stream", "expected_group"),
    [
        ("cartoon:tasks:collect", "cartoon:workers:collect"),
        ("cartoon:tasks:select_topic", "cartoon:workers:select_topic"),
        ("cartoon:tasks:generate_scenario", "cartoon:workers:generate_scenario"),
        ("cartoon:tasks:review_scenario", "cartoon:workers:review_scenario"),
    ],
)
def test_resolve_consumer_group_known_stream(
    stream: str,
    expected_group: str,
) -> None:
    assert resolve_consumer_group(stream) == expected_group


def test_resolve_consumer_group_unknown_stream_raises() -> None:
    with pytest.raises(StreamNotFoundError) as exc_info:
        resolve_consumer_group("cartoon:tasks:unknown")

    assert exc_info.value.stream == "cartoon:tasks:unknown"
