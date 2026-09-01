"""In-memory artifact repository fake."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from persistence.errors import (
    PersistenceDuplicateError,
    PersistenceNotFoundError,
    PersistenceTransactionError,
)
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.types import (
    AiInvocationInsertSpec,
    AiInvocationRecord,
    ArtifactCreateSpec,
    ArtifactRecord,
    ArtifactType,
    JsonValue,
)


class InMemoryArtifactRepo:
    """Dict-backed artifact repository for tests."""

    def __init__(
        self,
        *,
        transaction_manager: InMemoryTransactionManager | None = None,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._content: dict[str, JsonValue] = {}
        self._invocations: list[AiInvocationRecord] = []
        if transaction_manager is not None:
            transaction_manager.register_store(self._snapshot, self._restore)

    def _snapshot(self) -> dict[str, object]:
        return {
            "artifacts": copy.deepcopy(self._artifacts),
            "content": copy.deepcopy(self._content),
            "invocations": copy.deepcopy(self._invocations),
        }

    def _restore(self, snapshot: dict[str, object]) -> None:
        self._artifacts = snapshot["artifacts"]  # type: ignore[assignment]
        self._content = snapshot["content"]  # type: ignore[assignment]
        self._invocations = snapshot["invocations"]  # type: ignore[assignment]

    def _require_active_transaction(self, operation: str) -> None:
        if (
            self._transaction_manager is None
            or not self._transaction_manager.is_in_transaction()
        ):
            raise PersistenceTransactionError(
                f"Operation {operation} requires an active transaction"
            )

    def create_artifact(self, spec: ArtifactCreateSpec) -> ArtifactRecord:
        operation = "create_artifact"
        if spec.is_active:
            self._require_active_transaction(operation)
        artifact_id = str(uuid4())
        now = datetime.now(UTC)
        for record in self._artifacts.values():
            if (
                record.workflow_id == spec.workflow_id
                and record.artifact_type == spec.artifact_type
                and record.version == spec.version
            ):
                raise PersistenceDuplicateError(
                    f"Duplicate artifact version for workflow {spec.workflow_id}"
                )
        if spec.is_active:
            for key, record in list(self._artifacts.items()):
                if (
                    record.workflow_id == spec.workflow_id
                    and record.artifact_type == spec.artifact_type
                    and record.is_active
                ):
                    self._artifacts[key] = ArtifactRecord(
                        artifact_id=record.artifact_id,
                        workflow_id=record.workflow_id,
                        artifact_type=record.artifact_type,
                        name=record.name,
                        version=record.version,
                        logical_version=record.logical_version,
                        is_active=False,
                        created_at=record.created_at,
                        content_hash=record.content_hash,
                    )
        record = ArtifactRecord(
            artifact_id=artifact_id,
            workflow_id=spec.workflow_id,
            artifact_type=spec.artifact_type,
            name=spec.name,
            version=spec.version,
            logical_version=spec.logical_version,
            is_active=spec.is_active,
            created_at=now,
            content_hash=None,
        )
        self._artifacts[artifact_id] = record
        self._content[artifact_id] = spec.content
        return record

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self._artifacts.get(artifact_id)

    def get_artifact_content(self, artifact_id: str) -> JsonValue:
        if artifact_id not in self._content:
            raise PersistenceNotFoundError(f"Artifact content {artifact_id} not found")
        return self._content[artifact_id]

    def list_artifacts(
        self,
        workflow_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        active_only: bool = False,
    ) -> Sequence[ArtifactRecord]:
        records = [
            record
            for record in self._artifacts.values()
            if record.workflow_id == workflow_id
            and (artifact_type is None or record.artifact_type == artifact_type)
            and (not active_only or record.is_active)
        ]
        return sorted(records, key=lambda r: r.version)

    def get_active_artifact(
        self, workflow_id: str, artifact_type: ArtifactType
    ) -> ArtifactRecord | None:
        records = self.list_artifacts(
            workflow_id,
            artifact_type=artifact_type,
            active_only=True,
        )
        return records[0] if records else None

    def append_ai_invocation(
        self, spec: AiInvocationInsertSpec
    ) -> AiInvocationRecord:
        invocation_id = str(uuid4())
        record = AiInvocationRecord(
            invocation_id=invocation_id,
            workflow_id=spec.workflow_id,
            task_id=spec.task_id,
            agent_name=spec.agent_name,
            agent_version=spec.agent_version,
            prompt_version=spec.prompt_version,
            provider=spec.provider,
            model=spec.model,
            input_artifact_id=spec.input_artifact_id,
            output_artifact_id=spec.output_artifact_id,
            attempt=spec.attempt,
            started_at=spec.started_at,
            completed_at=spec.completed_at,
            status=spec.status,
            input_tokens=spec.input_tokens,
            output_tokens=spec.output_tokens,
            estimated_cost_usd=spec.estimated_cost_usd,
        )
        self._invocations.append(record)
        return record

    def list_ai_invocations(
        self, workflow_id: str, *, task_id: str | None = None
    ) -> Sequence[AiInvocationRecord]:
        return [
            record
            for record in self._invocations
            if record.workflow_id == workflow_id
            and (task_id is None or record.task_id == task_id)
        ]
