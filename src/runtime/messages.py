"""Internal bootstrap and lifecycle error message templates (MOD-RT-INV-027)."""

from __future__ import annotations

from .types import ProcessKind


def bootstrap_persistence_message(*, host: str, port: int) -> str:
    """Persistence bootstrap failure — no credentials or secrets."""
    return f"dependency=persistence host={host} port={port} detail=unavailable"


def bootstrap_queue_message(*, host: str, port: int) -> str:
    """Task queue bootstrap failure — no credentials or secrets."""
    return f"dependency=task_queue host={host} port={port} detail=unavailable"


def startup_http_message(*, host: str, port: int, reason: str) -> str:
    """HTTP bind/start failure — bounded host/port only."""
    return f"host={host} port={port} reason={reason}"


def shutdown_grace_message(*, kind: ProcessKind, grace_seconds: float) -> str:
    """Shutdown grace exceeded."""
    return f"process_kind={kind.value} grace_seconds={grace_seconds} detail=exceeded"
