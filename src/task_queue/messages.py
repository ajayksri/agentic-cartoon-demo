"""Internal error message templates (LLD §3.8)."""

from __future__ import annotations


def connection_message(*, host: str, port: int, reason: str) -> str:
    return f"Redis connection failed ({host}:{port}): {reason}"


def unavailable_message(*, operation: str, reason: str) -> str:
    return f"Redis unavailable during {operation}: {reason}"


def invalid_message_message(
    *,
    stream: str,
    delivery_id: str | None,
    missing_fields: tuple[str, ...],
) -> str:
    fields = ", ".join(missing_fields) if missing_fields else "unknown"
    suffix = f", delivery_id={delivery_id}" if delivery_id else ""
    return (
        f"Invalid task message on stream '{stream}'{suffix}: "
        f"missing or invalid fields: {fields}"
    )


def consumer_group_message(*, stream: str, group: str, reason: str) -> str:
    return f"Consumer group error on stream '{stream}', group '{group}': {reason}"


def ack_message(*, delivery_id: str, reason: str) -> str:
    return f"ACK failed for delivery_id '{delivery_id}': {reason}"


def stream_not_found_message(*, stream: str) -> str:
    return f"Stream not found: '{stream}'"
