"""In-memory artifact repository fake for workflow read-model tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from persistence.errors import PersistenceNotFoundError
from persistence.types import (
    AiInvocationInsertSpec,
    AiInvocationRecord,
    ArtifactCreateSpec,
    ArtifactRecord,
    ArtifactType,
    InvocationStatus,
    JsonValue,
)


class InMemoryArtifactRepo:
    """Fixture artifacts for WF-TC-020/021 output package assembly."""

    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._content: dict[str, JsonValue] = {}
        self._invocations: list[AiInvocationRecord] = []
        self._seed_failed_output_fixture()

    def _seed_failed_output_fixture(self) -> None:
        workflow_id = "wf-output-failed"
        self.seed_active_artifacts(
            workflow_id=workflow_id,
            topic={
                "selected_topic": "Partial topic",
                "rationale": "Incomplete run",
            },
        )

    def create_artifact(self, spec: ArtifactCreateSpec) -> ArtifactRecord:
        artifact_id = str(uuid4())
        now = datetime.now(UTC)
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
            r
            for r in self._artifacts.values()
            if r.workflow_id == workflow_id
            and (artifact_type is None or r.artifact_type == artifact_type)
            and (not active_only or r.is_active)
        ]
        return sorted(records, key=lambda r: r.version)

    def get_active_artifact(
        self, workflow_id: str, artifact_type: ArtifactType
    ) -> ArtifactRecord | None:
        records = self.list_artifacts(
            workflow_id, artifact_type=artifact_type, active_only=True
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
            inv
            for inv in self._invocations
            if inv.workflow_id == workflow_id
            and (task_id is None or inv.task_id == task_id)
        ]

    def seed_active_artifacts(
        self,
        *,
        workflow_id: str,
        topic: dict[str, object] | None = None,
        scenario: dict[str, object] | None = None,
        critic: dict[str, object] | None = None,
    ) -> None:
        if topic is not None:
            self.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.TOPIC_SELECTION,
                    name="topic",
                    version=1,
                    logical_version=1,
                    content=topic,
                    is_active=True,
                )
            )
        if scenario is not None:
            self.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.SCENARIO,
                    name="scenario",
                    version=1,
                    logical_version=1,
                    content=scenario,
                    is_active=True,
                )
            )
        if critic is not None:
            self.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.CRITIC_REVIEW,
                    name="critic",
                    version=1,
                    logical_version=1,
                    content=critic,
                    is_active=True,
                )
            )

    def seed_ai_invocations(
        self,
        *,
        workflow_id: str,
        occurred_at: datetime,
        invocation_ids: tuple[str, ...],
    ) -> None:
        for invocation_id in invocation_ids:
            self._invocations.append(
                AiInvocationRecord(
                    invocation_id=invocation_id,
                    workflow_id=workflow_id,
                    task_id="task-seed",
                    agent_name="critic",
                    agent_version="1",
                    prompt_version="1",
                    provider="fake",
                    model="fake-model",
                    input_artifact_id=None,
                    output_artifact_id=None,
                    attempt=1,
                    started_at=occurred_at,
                    completed_at=occurred_at,
                    status=InvocationStatus.SUCCESS,
                    input_tokens=10,
                    output_tokens=20,
                    estimated_cost_usd=Decimal("0.01"),
                )
            )
