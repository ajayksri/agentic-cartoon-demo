"""Shared handler helpers (LLD §4.11)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Stage handler glue — persists AI invocation audit
# records and artifacts in the same transaction as workflow transitions.

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from agents.errors import AgentInputValidationError, AgentOutputValidationError
from agents.types import CandidateStory
from config.types import AgentId, InjectionId
from persistence.types import (
    AiInvocationInsertSpec,
    ArtifactCreateSpec,
    ArtifactType,
    InvocationStatus,
)
from providers.errors import ProviderError
from providers.types import ProviderErrorClass

from ..constants import ARTIFACT_SCHEMA_V1, ARTIFACT_SCHEMA_VERSION
from ..context import AgentRunContextBuilder
from ..errors import TaskExecutionError
from ..messages import execution_error_message
from ..types import TaskExecutionContext

if TYPE_CHECKING:
    from ..types import TaskHandlerResult


_AGENT_NAMES: dict[AgentId, str] = {
    AgentId.TOPIC_SELECTOR: "topic_selector",
    AgentId.SCENARIO_GENERATOR: "scenario_generator",
    AgentId.CRITIC: "critic",
}


@dataclass(frozen=True, slots=True)
class AiInvocationDraft:
    """Intermediate before append_ai_invocation inside transaction."""

    agent_name: str
    agent_version: str
    prompt_version: str
    provider: str
    model: str
    input_artifact_id: str | None
    output_artifact_id: str | None
    attempt: int
    started_at: datetime
    completed_at: datetime
    status: InvocationStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None


class HandlerSupport:
    """Shared persistence and agent-stage helpers for stage handlers."""

    @staticmethod
    def create_artifact(
        *,
        context: TaskExecutionContext,
        artifact_type: ArtifactType,
        content: dict[str, object],
        logical_version: int,
        name: str | None = None,
    ) -> str:
        if not context.transaction_manager.is_in_transaction():
            raise RuntimeError(
                "create_artifact requires an active transaction; use transaction_manager.transaction()"
            )
        enriched = dict(content)
        enriched[ARTIFACT_SCHEMA_VERSION] = ARTIFACT_SCHEMA_V1
        spec = ArtifactCreateSpec(
            workflow_id=context.delivery.message.workflow_id,
            artifact_type=artifact_type,
            name=name or artifact_type.value,
            version=logical_version,
            logical_version=logical_version,
            content=enriched,
            is_active=True,
        )
        record = context.artifact_repo.create_artifact(spec)
        if isinstance(record, str):
            return record
        return record.artifact_id

    @staticmethod
    def append_ai_invocation(
        context: TaskExecutionContext,
        draft: AiInvocationDraft,
    ) -> str:
        spec = AiInvocationInsertSpec(
            workflow_id=context.delivery.message.workflow_id,
            task_id=context.delivery.message.task_id,
            agent_name=draft.agent_name,
            agent_version=draft.agent_version,
            prompt_version=draft.prompt_version,
            provider=draft.provider,
            model=draft.model,
            input_artifact_id=draft.input_artifact_id,
            output_artifact_id=draft.output_artifact_id,
            attempt=draft.attempt,
            started_at=draft.started_at,
            completed_at=draft.completed_at,
            status=draft.status,
            input_tokens=draft.input_tokens,
            output_tokens=draft.output_tokens,
            estimated_cost_usd=draft.estimated_cost_usd,
        )
        record = context.artifact_repo.append_ai_invocation(spec)
        return record.invocation_id

    @staticmethod
    def load_active_artifact_json(
        context: TaskExecutionContext,
        artifact_type: ArtifactType,
    ) -> tuple[object, dict[str, object]]:
        record = context.artifact_repo.get_active_artifact(
            context.delivery.message.workflow_id,
            artifact_type,
        )
        if record is None:
            raise TaskExecutionError(
                execution_error_message(
                    workflow_id=context.delivery.message.workflow_id,
                    task_id=context.delivery.message.task_id,
                    task_type=context.delivery.message.task_type,
                    detail=f"Missing prerequisite artifact {artifact_type.value}",
                ),
                workflow_id=context.delivery.message.workflow_id,
                task_id=context.delivery.message.task_id,
                task_type=context.delivery.message.task_type,
                retryable=False,
            )
        raw = context.artifact_repo.get_artifact_content(record.artifact_id)
        if isinstance(raw, dict):
            content = raw
        else:
            content = json.loads(str(raw))
        return record, content

    @staticmethod
    def map_story_records_to_candidates(
        content: dict[str, object],
    ) -> tuple[CandidateStory, ...]:
        candidates_raw = content.get("candidates", [])
        if not isinstance(candidates_raw, list):
            return ()
        candidates: list[CandidateStory] = []
        for entry in candidates_raw:
            if not isinstance(entry, dict):
                continue
            candidates.append(
                CandidateStory(
                    source_id=str(entry.get("source_id", "")),
                    title=entry.get("title") if entry.get("title") is not None else None,
                    url=entry.get("url") if entry.get("url") is not None else None,
                    score=int(entry["score"]) if entry.get("score") is not None else None,
                    comment_count=int(entry["comment_count"])
                    if entry.get("comment_count") is not None
                    else None,
                    rank_score=float(entry["rank_score"])
                    if entry.get("rank_score") is not None
                    else None,
                )
            )
        return tuple(candidates)

    @staticmethod
    def run_agent_stage(
        *,
        context: TaskExecutionContext,
        agent_id: AgentId,
        started_at: datetime,
        input_artifact_id: str | None,
        agent_call: Callable[[], object],
        map_audit_status: Callable[[BaseException | None], InvocationStatus | str],
    ) -> tuple[object, AiInvocationDraft | None]:
        agent_config = context.config.get_agent_config(agent_id)
        agent_context = AgentRunContextBuilder.build(
            agent_id=agent_id,
            delivery=context.delivery,
            config=context.config,
            model_provider_factory=context.model_provider_factory,
            logger=context.logger,
            meter=context.meter,
            tracer=context.tracer,
            attempt=context.delivery.message.attempt,
        )
        try:
            output = agent_call()
        except (
            ProviderError,
            AgentOutputValidationError,
            AgentInputValidationError,
        ) as err:
            status = map_audit_status(err)
            if isinstance(status, str):
                invocation_status = InvocationStatus(status)
            else:
                invocation_status = status
            failure_draft = AiInvocationDraft(
                agent_name=_AGENT_NAMES[agent_id],
                agent_version="1",
                prompt_version="unknown",
                provider=agent_context.provider.provider_id.value,
                model=agent_config.model,
                input_artifact_id=input_artifact_id,
                output_artifact_id=None,
                attempt=context.delivery.message.attempt,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                status=invocation_status,
            )
            HandlerSupport.append_ai_invocation(context, failure_draft)
            context.failure_injection.invoke_if_active(InjectionId.FINJ_WKR_POST_AGENT)
            raise
        context.failure_injection.invoke_if_active(InjectionId.FINJ_WKR_POST_AGENT)
        return output, None

    @staticmethod
    def map_agent_error_to_invocation_status(
        err: BaseException | None,
    ) -> InvocationStatus:
        if err is None:
            return InvocationStatus.SUCCESS
        if isinstance(err, AgentOutputValidationError | AgentInputValidationError):
            return InvocationStatus.VALIDATION_FAILED
        if isinstance(err, ProviderError):
            if err.error_class == ProviderErrorClass.TIMEOUT:
                return InvocationStatus.TIMEOUT
            return InvocationStatus.PROVIDER_ERROR
        return InvocationStatus.PROVIDER_ERROR
