"""Pre-code test mold for TQ-005 — ConsumerGroupManager (LLD §3.3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from task_queue import ConsumerGroupError


def test_ensure_group_creates_stream_and_group() -> None:
    """ensure_group calls XGROUP CREATE with MKSTREAM."""
    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    manager = ConsumerGroupManager(client)

    manager.ensure_group("cartoon:tasks:collect", "cartoon:workers:collect")

    client.xgroup_create.assert_called_once_with(
        "cartoon:tasks:collect",
        "cartoon:workers:collect",
        id="0",
        mkstream=True,
    )


def test_ensure_group_busygroup_is_idempotent() -> None:
    """Second ensure_group with BUSYGROUP succeeds without error (TQ-TC-013 seam)."""
    from redis.exceptions import ResponseError

    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    client.xgroup_create.side_effect = [
        None,
        ResponseError("BUSYGROUP Consumer Group name already exists"),
    ]
    manager = ConsumerGroupManager(client)

    manager.ensure_group("cartoon:tasks:collect", "cartoon:workers:collect")
    manager.ensure_group("cartoon:tasks:collect", "cartoon:workers:collect")


def test_ensure_group_non_busygroup_error_raises_consumer_group_error() -> None:
    """Non-BUSYGROUP XGROUP CREATE failure raises ConsumerGroupError."""
    from redis.exceptions import ResponseError

    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    client.xgroup_create.side_effect = ResponseError("NOGROUP No such key")
    manager = ConsumerGroupManager(client)

    with pytest.raises(ConsumerGroupError) as exc_info:
        manager.ensure_group("cartoon:tasks:collect", "cartoon:workers:collect")

    assert exc_info.value.stream == "cartoon:tasks:collect"
    assert exc_info.value.group == "cartoon:workers:collect"


def test_group_exists_returns_true_when_group_present() -> None:
    """group_exists returns True when group appears in XINFO GROUPS."""
    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    client.xinfo_groups.return_value = [
        {"name": "cartoon:workers:collect"},
        {"name": "other-group"},
    ]
    manager = ConsumerGroupManager(client)

    assert manager.group_exists("cartoon:tasks:collect", "cartoon:workers:collect") is True


def test_group_exists_false_when_stream_absent() -> None:
    """group_exists returns False when stream does not exist."""
    from redis.exceptions import ResponseError

    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    client.xinfo_groups.side_effect = ResponseError("ERR no such key")
    manager = ConsumerGroupManager(client)

    assert manager.group_exists("missing:stream", "cartoon:workers:collect") is False


def test_group_exists_false_when_group_missing() -> None:
    """group_exists returns False when stream exists but group is absent."""
    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    client.xinfo_groups.return_value = [{"name": "other-group"}]
    manager = ConsumerGroupManager(client)

    assert manager.group_exists("cartoon:tasks:collect", "cartoon:workers:collect") is False


def test_ensure_group_passes_custom_start_id() -> None:
    """ensure_group forwards custom start_id to XGROUP CREATE."""
    from task_queue.consumer_groups import ConsumerGroupManager

    client = MagicMock()
    manager = ConsumerGroupManager(client)

    manager.ensure_group("cartoon:tasks:collect", "cartoon:workers:collect", start_id="$")

    client.xgroup_create.assert_called_once_with(
        "cartoon:tasks:collect",
        "cartoon:workers:collect",
        id="$",
        mkstream=True,
    )
