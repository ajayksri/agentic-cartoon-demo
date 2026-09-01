"""Unit tests for runtime.messages (RT-001)."""

from __future__ import annotations

from runtime.messages import (
    bootstrap_persistence_message,
    bootstrap_queue_message,
    shutdown_grace_message,
    startup_http_message,
)
from runtime.types import ProcessKind

_FORBIDDEN_FRAGMENTS = (
    "password=",
    "postgresql://",
    "api_key",
    "secret",
    "token=",
)


def test_bootstrap_persistence_message_omits_secrets() -> None:
    message = bootstrap_persistence_message(host="db.internal", port=5432)
    lowered = message.lower()
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in lowered
    assert "host=db.internal" in message
    assert "port=5432" in message


def test_bootstrap_queue_message_omits_secrets() -> None:
    message = bootstrap_queue_message(host="redis.internal", port=6379)
    lowered = message.lower()
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in lowered


def test_startup_http_message_includes_bounded_fields_only() -> None:
    message = startup_http_message(host="0.0.0.0", port=8000, reason="address_in_use")
    assert "host=0.0.0.0" in message
    assert "port=8000" in message
    assert "reason=address_in_use" in message


def test_shutdown_grace_message_includes_process_kind() -> None:
    message = shutdown_grace_message(kind=ProcessKind.WORKER, grace_seconds=30.0)
    assert "process_kind=worker" in message
    assert "grace_seconds=30.0" in message
