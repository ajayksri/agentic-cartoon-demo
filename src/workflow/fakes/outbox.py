"""In-memory outbox repository fake."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from persistence.errors import PersistenceNotFoundError
from persistence.types import OutboxEntry, OutboxInsertSpec, OutboxStatus


class InMemoryOutboxRepo:
    """Tracks PENDING outbox rows for workflow contract tests."""

    def __init__(self) -> None:
        self._entries: dict[str, OutboxEntry] = {}

    def insert(self, spec: OutboxInsertSpec) -> OutboxEntry:
        outbox_id = str(uuid4())
        now = datetime.now(UTC)
        entry = OutboxEntry(
            outbox_id=outbox_id,
            workflow_id=spec.workflow_id,
            task_id=spec.task_id,
            task_type=spec.task_type,
            payload_reference=spec.payload_reference,
            idempotency_key=spec.idempotency_key,
            status=OutboxStatus.PENDING,
            created_at=now,
            published_at=None,
        )
        self._entries[outbox_id] = entry
        return entry

    def fetch_unpublished(self, limit: int) -> Sequence[OutboxEntry]:
        pending = [e for e in self._entries.values() if e.status == OutboxStatus.PENDING]
        pending.sort(key=lambda e: e.created_at)
        return pending[:limit]

    def mark_published(
        self, outbox_id: str, *, published_at: datetime
    ) -> OutboxEntry:
        existing = self._entries.get(outbox_id)
        if existing is None:
            raise PersistenceNotFoundError(f"Outbox entry {outbox_id} not found")
        updated = OutboxEntry(
            outbox_id=existing.outbox_id,
            workflow_id=existing.workflow_id,
            task_id=existing.task_id,
            task_type=existing.task_type,
            payload_reference=existing.payload_reference,
            idempotency_key=existing.idempotency_key,
            status=OutboxStatus.PUBLISHED,
            created_at=existing.created_at,
            published_at=published_at,
        )
        self._entries[outbox_id] = updated
        return updated

    def list_unpublished_outbox_for_workflow(
        self, workflow_id: str
    ) -> Sequence[OutboxEntry]:
        return [
            e
            for e in self._entries.values()
            if e.workflow_id == workflow_id and e.status == OutboxStatus.PENDING
        ]
