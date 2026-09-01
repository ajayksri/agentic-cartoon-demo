"""Unit tests for worker stream/group mapping (RT-014, HLD §6.2)."""

from __future__ import annotations

from config.types import TaskType

from runtime.constants import WORKER_GROUP_BY_TASK_TYPE, WORKER_STREAM_BY_TASK_TYPE
from runtime.wiring.worker import build_worker_loop_config


def test_collect_role_maps_to_collect_stream_and_group() -> None:
    config = build_worker_loop_config(TaskType.COLLECT)

    assert config.stream == WORKER_STREAM_BY_TASK_TYPE[TaskType.COLLECT]
    assert config.consumer_group == WORKER_GROUP_BY_TASK_TYPE[TaskType.COLLECT]


def test_select_topic_role_maps_correctly() -> None:
    config = build_worker_loop_config(TaskType.SELECT_TOPIC)

    assert config.stream == "cartoon:tasks:select_topic"
    assert config.consumer_group == "cartoon:workers:select_topic"


def test_generate_scenario_role_maps_correctly() -> None:
    config = build_worker_loop_config(TaskType.GENERATE_SCENARIO)

    assert config.stream == WORKER_STREAM_BY_TASK_TYPE[TaskType.GENERATE_SCENARIO]
    assert config.consumer_group == WORKER_GROUP_BY_TASK_TYPE[TaskType.GENERATE_SCENARIO]


def test_review_scenario_role_maps_correctly() -> None:
    config = build_worker_loop_config(TaskType.REVIEW_SCENARIO)

    assert config.stream == WORKER_STREAM_BY_TASK_TYPE[TaskType.REVIEW_SCENARIO]
    assert config.consumer_group == WORKER_GROUP_BY_TASK_TYPE[TaskType.REVIEW_SCENARIO]


def test_consumer_name_contains_hostname_and_pid() -> None:
    import os
    import socket

    config = build_worker_loop_config(TaskType.COLLECT)

    assert str(os.getpid()) in config.consumer_name
    assert socket.gethostname() in config.consumer_name
