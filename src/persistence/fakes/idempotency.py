"""In-memory idempotency repository fake."""

from __future__ import annotations

import copy
import threading
from datetime import UTC, datetime

from persistence.errors import PersistenceTransactionError
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import (
    IdempotencyInsertResult,
    IdempotencyInsertSpec,
    IdempotencyOutcome,
    IdempotencyRecord,
)


class InMemoryIdempotencyRepo:
    """Dict-backed idempotency repository for tests."""

    def __init__(
        self,
        *,
        transaction_manager: InMemoryTransactionManager | None = None,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()
        if transaction_manager is not None:
            transaction_manager.register_store(self._snapshot, self._restore)

    def _snapshot(self) -> dict[str, IdempotencyRecord]:
        with self._lock:
            return copy.deepcopy(self._records)

    def _restore(self, snapshot: dict[str, IdempotencyRecord]) -> None:
        with self._lock:
            self._records = snapshot

    def _require_active_transaction(self, operation: str) -> None:
        if (
            self._transaction_manager is None
            or not self._transaction_manager.is_in_transaction()
        ):
            raise PersistenceTransactionError(
                f"Operation {operation} requires an active transaction"
            )

    def try_insert(self, spec: IdempotencyInsertSpec) -> IdempotencyInsertResult:
        operation = "try_insert"
        self._require_active_transaction(operation)
        with self._lock:
            existing = self._records.get(spec.idempotency_key)
            if existing is not None:
                return IdempotencyInsertResult(
                    outcome=IdempotencyOutcome.DUPLICATE,
                    record=existing,
                )
            record = IdempotencyRecord(
                idempotency_key=spec.idempotency_key,
                workflow_id=spec.workflow_id,
                task_id=spec.task_id,
                completed_at=datetime.now(UTC),
                result_artifact_id=spec.result_artifact_id,
            )
            self._records[spec.idempotency_key] = record
            return IdempotencyInsertResult(
                outcome=IdempotencyOutcome.INSERTED,
                record=record,
            )

    def get_by_key(self, idempotency_key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get(idempotency_key)
