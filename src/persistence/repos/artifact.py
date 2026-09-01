"""PostgreSQL artifact repository implementation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.errors import UniqueViolation

from persistence.errors import PersistenceDuplicateError, PersistenceNotFoundError
from persistence.repos._base import PostgresRepoBase, _jsonb
from persistence.repos._mappers import AiInvocationRow, ArtifactRow
from persistence.repos._sql import AI_INVOCATIONS, ARTIFACT_CONTENT, ARTIFACTS
from persistence.types import (
    AiInvocationInsertSpec,
    AiInvocationRecord,
    ArtifactCreateSpec,
    ArtifactRecord,
    ArtifactType,
    JsonValue,
)


class PostgresArtifactRepo(PostgresRepoBase):
    """Artifact metadata, JSONB content, and AI invocation audit records."""

    def create_artifact(self, spec: ArtifactCreateSpec) -> ArtifactRecord:
        operation = "create_artifact"
        if spec.is_active:
            self._require_active_transaction(operation)
        artifact_id = str(uuid4())
        now = datetime.now(UTC)
        artifact_type_token = self._mapper.artifact_type_to_db(spec.artifact_type)
        try:
            if spec.is_active:
                conn = self._connection()
                self._insert_artifact_rows(
                    conn,
                    artifact_id=artifact_id,
                    spec=spec,
                    artifact_type_token=artifact_type_token,
                    now=now,
                    deactivate_active=True,
                )
            else:
                with self._borrow_connection() as conn:
                    self._insert_artifact_rows(
                        conn,
                        artifact_id=artifact_id,
                        spec=spec,
                        artifact_type_token=artifact_type_token,
                        now=now,
                        deactivate_active=False,
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
            self._record_success(operation)
            return record
        except UniqueViolation as exc:
            duplicate = PersistenceDuplicateError(
                f"Duplicate artifact version for workflow {spec.workflow_id}"
            )
            self._log_error(operation, duplicate, spec.workflow_id)
            raise duplicate from exc
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=spec.workflow_id)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        operation = "get_artifact"
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    SELECT artifact_id, workflow_id, artifact_type, name, version,
                           logical_version, is_active, content_hash, created_at
                    FROM artifacts
                    WHERE artifact_id = %s
                    """,
                    (artifact_id,),
                    prepare=False,
                ).fetchone()
            if row is None:
                return None
            record = self._mapper.to_artifact_record(self._artifact_row_from_dict(row))
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=artifact_id)

    def get_artifact_content(self, artifact_id: str) -> JsonValue:
        operation = "get_artifact_content"
        try:
            with self._borrow_connection() as conn:
                row = conn.execute(
                    """
                    SELECT content
                    FROM artifact_content
                    WHERE artifact_id = %s
                    """,
                    (artifact_id,),
                    prepare=False,
                ).fetchone()
            if row is None:
                not_found = PersistenceNotFoundError(
                    f"Artifact content {artifact_id} not found"
                )
                self._log_error(operation, not_found, artifact_id)
                raise not_found
            self._record_success(operation)
            return row["content"]  # type: ignore[return-value]
        except PersistenceNotFoundError:
            raise
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=artifact_id)

    def list_artifacts(
        self,
        workflow_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        active_only: bool = False,
    ) -> Sequence[ArtifactRecord]:
        operation = "list_artifacts"
        clauses = ["workflow_id = %s"]
        params: list[object] = [workflow_id]
        if artifact_type is not None:
            clauses.append("artifact_type = %s")
            params.append(self._mapper.artifact_type_to_db(artifact_type))
        if active_only:
            clauses.append("is_active = TRUE")
        query = f"""
            SELECT artifact_id, workflow_id, artifact_type, name, version,
                   logical_version, is_active, content_hash, created_at
            FROM artifacts
            WHERE {' AND '.join(clauses)}
            ORDER BY version ASC
        """
        try:
            with self._borrow_connection() as conn:
                rows = conn.execute(query, tuple(params), prepare=False).fetchall()
            records = [
                self._mapper.to_artifact_record(self._artifact_row_from_dict(row))
                for row in rows
            ]
            self._record_success(operation)
            return records
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

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
        operation = "append_ai_invocation"
        invocation_id = str(uuid4())
        try:
            with self._borrow_connection() as conn:
                conn.execute(
                    AI_INVOCATIONS,
                    (
                        invocation_id,
                        spec.workflow_id,
                        spec.task_id,
                        spec.agent_name,
                        spec.agent_version,
                        spec.prompt_version,
                        spec.provider,
                        spec.model,
                        spec.input_artifact_id,
                        spec.output_artifact_id,
                        spec.attempt,
                        spec.started_at,
                        spec.completed_at,
                        self._mapper.invocation_status_to_db(spec.status),
                        spec.input_tokens,
                        spec.output_tokens,
                        spec.estimated_cost_usd,
                    ),
                    prepare=False,
                )
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
            self._record_success(operation)
            return record
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=invocation_id)

    def list_ai_invocations(
        self, workflow_id: str, *, task_id: str | None = None
    ) -> Sequence[AiInvocationRecord]:
        operation = "list_ai_invocations"
        if task_id is not None:
            query = """
                SELECT invocation_id, workflow_id, task_id, agent_name, agent_version,
                       prompt_version, provider, model, input_artifact_id,
                       output_artifact_id, attempt, started_at, completed_at, status,
                       input_tokens, output_tokens, estimated_cost_usd
                FROM ai_invocations
                WHERE workflow_id = %s AND task_id = %s
                ORDER BY started_at ASC
            """
            params: tuple[object, ...] = (workflow_id, task_id)
        else:
            query = """
                SELECT invocation_id, workflow_id, task_id, agent_name, agent_version,
                       prompt_version, provider, model, input_artifact_id,
                       output_artifact_id, attempt, started_at, completed_at, status,
                       input_tokens, output_tokens, estimated_cost_usd
                FROM ai_invocations
                WHERE workflow_id = %s
                ORDER BY started_at ASC
            """
            params = (workflow_id,)
        try:
            with self._borrow_connection() as conn:
                rows = conn.execute(query, params, prepare=False).fetchall()
            records = [
                self._mapper.to_ai_invocation_record(
                    AiInvocationRow(
                        invocation_id=str(row["invocation_id"]),
                        workflow_id=str(row["workflow_id"]),
                        task_id=str(row["task_id"]),
                        agent_name=str(row["agent_name"]),
                        agent_version=str(row["agent_version"]),
                        prompt_version=str(row["prompt_version"]),
                        provider=str(row["provider"]),
                        model=str(row["model"]),
                        input_artifact_id=(
                            str(row["input_artifact_id"])
                            if row.get("input_artifact_id") is not None
                            else None
                        ),
                        output_artifact_id=(
                            str(row["output_artifact_id"])
                            if row.get("output_artifact_id") is not None
                            else None
                        ),
                        attempt=int(row["attempt"]),  # type: ignore[arg-type]
                        started_at=row["started_at"],  # type: ignore[arg-type]
                        completed_at=row.get("completed_at"),  # type: ignore[arg-type]
                        status=str(row["status"]),
                        input_tokens=row.get("input_tokens"),  # type: ignore[arg-type]
                        output_tokens=row.get("output_tokens"),  # type: ignore[arg-type]
                        estimated_cost_usd=row.get("estimated_cost_usd"),  # type: ignore[arg-type]
                    )
                )
                for row in rows
            ]
            self._record_success(operation)
            return records
        except Exception as exc:
            self._raise_mapped(exc, operation=operation, entity_id=workflow_id)

    def _insert_artifact_rows(
        self,
        conn: object,
        *,
        artifact_id: str,
        spec: ArtifactCreateSpec,
        artifact_type_token: str,
        now: datetime,
        deactivate_active: bool,
    ) -> None:
        if deactivate_active:
            conn.execute(  # type: ignore[attr-defined]
                """
                UPDATE artifacts
                SET is_active = FALSE
                WHERE workflow_id = %s
                  AND artifact_type = %s
                  AND is_active = TRUE
                """,
                (spec.workflow_id, artifact_type_token),
                prepare=False,
            )
        conn.execute(  # type: ignore[attr-defined]
            ARTIFACTS,
            (
                artifact_id,
                spec.workflow_id,
                artifact_type_token,
                spec.name,
                spec.version,
                spec.logical_version,
                spec.is_active,
                None,
                now,
            ),
            prepare=False,
        )
        conn.execute(  # type: ignore[attr-defined]
            ARTIFACT_CONTENT,
            (artifact_id, _jsonb(spec.content), now),
            prepare=False,
        )

    @staticmethod
    def _artifact_row_from_dict(row: dict[str, Any]) -> ArtifactRow:
        return ArtifactRow(
            artifact_id=str(row["artifact_id"]),
            workflow_id=str(row["workflow_id"]),
            artifact_type=str(row["artifact_type"]),
            name=str(row["name"]),
            version=int(row["version"]),  # type: ignore[arg-type]
            logical_version=int(row["logical_version"]),  # type: ignore[arg-type]
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],  # type: ignore[arg-type]
            content_hash=(
                str(row["content_hash"])
                if row.get("content_hash") is not None
                else None
            ),
        )
