"""Stream→consumer-group convention registry (LLD §2.2)."""

from __future__ import annotations

from dataclasses import dataclass

from config.types import TaskType

from .errors import StreamNotFoundError
from .messages import stream_not_found_message


@dataclass(frozen=True, slots=True)
class StreamConvention:
    stream: str
    consumer_group: str
    task_type: TaskType


STREAM_CONVENTIONS: dict[str, StreamConvention] = {
    "cartoon:tasks:collect": StreamConvention(
        stream="cartoon:tasks:collect",
        consumer_group="cartoon:workers:collect",
        task_type=TaskType.COLLECT,
    ),
    "cartoon:tasks:select_topic": StreamConvention(
        stream="cartoon:tasks:select_topic",
        consumer_group="cartoon:workers:select_topic",
        task_type=TaskType.SELECT_TOPIC,
    ),
    "cartoon:tasks:generate_scenario": StreamConvention(
        stream="cartoon:tasks:generate_scenario",
        consumer_group="cartoon:workers:generate_scenario",
        task_type=TaskType.GENERATE_SCENARIO,
    ),
    "cartoon:tasks:review_scenario": StreamConvention(
        stream="cartoon:tasks:review_scenario",
        consumer_group="cartoon:workers:review_scenario",
        task_type=TaskType.REVIEW_SCENARIO,
    ),
}


def resolve_consumer_group(stream: str) -> str:
    """Return primary worker consumer group for stream."""
    convention = STREAM_CONVENTIONS.get(stream)
    if convention is None:
        raise StreamNotFoundError(
            stream_not_found_message(stream=stream),
            stream=stream,
        )
    return convention.consumer_group
