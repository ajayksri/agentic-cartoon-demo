"""Read model assembly for workflow queries (LLD §8)."""

from __future__ import annotations

from datetime import UTC

from persistence.protocols import ArtifactRepo, WorkflowRepo
from persistence.types import ArtifactType, WorkflowRecord

from .constants import TERMINAL_STATES
from .records import to_domain_transition, to_domain_workflow_state
from .types import (
    TimelineEvent,
    WorkflowHistory,
    WorkflowOutput,
    WorkflowState,
    WorkflowStatus,
    WorkflowTimeline,
)

_EVENT_TYPE_RANK = {
    "transition": 0,
    "task_enqueued": 1,
    "ai_invocation": 2,
}


class ReadModelAssembler:
    """Assembles workflow read models without mutating state."""

    def __init__(
        self,
        *,
        workflow_repo: WorkflowRepo,
        artifact_repo: ArtifactRepo,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._artifact_repo = artifact_repo

    def assemble_status(self, record: WorkflowRecord) -> WorkflowStatus:
        return WorkflowStatus(
            workflow_id=record.workflow_id,
            state=to_domain_workflow_state(record.state.value),
            state_version=record.state_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            revision_count=record.revision_count,
            failure_reason=record.failure_reason,
        )

    def assemble_history(self, workflow_id: str) -> WorkflowHistory:
        rows = self._workflow_repo.list_transitions(workflow_id)
        transitions = tuple(to_domain_transition(row) for row in rows)
        return WorkflowHistory(workflow_id=workflow_id, transitions=transitions)

    def assemble_output(self, *, workflow: WorkflowRecord) -> WorkflowOutput:
        workflow_id = workflow.workflow_id
        state = to_domain_workflow_state(workflow.state.value)
        package: dict[str, object] = {}

        source = self._artifact_repo.get_active_artifact(
            workflow_id, ArtifactType.COLLECTED_STORIES
        )
        if source is not None:
            content = self._artifact_repo.get_artifact_content(source.artifact_id)
            stories = content.get("stories", []) if isinstance(content, dict) else []
            package["source"] = {
                "artifact_id": source.artifact_id,
                "version": source.version,
                "logical_version": source.logical_version,
                "story_count": len(stories) if isinstance(stories, list) else 0,
                "collected_at": source.created_at.astimezone(UTC).isoformat(),
                "content": content,
            }

        topic = self._artifact_repo.get_active_artifact(
            workflow_id, ArtifactType.TOPIC_SELECTION
        )
        if topic is not None:
            content = self._artifact_repo.get_artifact_content(topic.artifact_id)
            if isinstance(content, dict):
                package["topic"] = {
                    "artifact_id": topic.artifact_id,
                    "version": topic.version,
                    "selected_topic": content.get("selected_topic", ""),
                    "rationale": content.get("rationale", ""),
                    "confidence": content.get("confidence"),
                    "content": content,
                }

        scenario = self._artifact_repo.get_active_artifact(
            workflow_id, ArtifactType.SCENARIO
        )
        if scenario is not None:
            content = self._artifact_repo.get_artifact_content(scenario.artifact_id)
            if isinstance(content, dict):
                package["scenario"] = {
                    "artifact_id": scenario.artifact_id,
                    "version": scenario.version,
                    "logical_version": scenario.logical_version,
                    "premise": content.get("premise", ""),
                    "characters": content.get("characters", []),
                    "panels": content.get("panels", []),
                    "punchline": content.get("punchline"),
                    "content": content,
                }

        critic = self._artifact_repo.get_active_artifact(
            workflow_id, ArtifactType.CRITIC_REVIEW
        )
        if critic is not None:
            content = self._artifact_repo.get_artifact_content(critic.artifact_id)
            if isinstance(content, dict):
                package["critic"] = {
                    "artifact_id": critic.artifact_id,
                    "version": critic.version,
                    "verdict": content.get("verdict", ""),
                    "dimensions": content.get("dimensions", {}),
                    "content": content,
                }

        transitions = self._workflow_repo.list_transitions(workflow_id)
        invocations = self._artifact_repo.list_ai_invocations(workflow_id)
        invocation_summaries = [
            {
                "invocation_id": inv.invocation_id,
                "agent_name": inv.agent_name,
                "provider": inv.provider,
                "model": inv.model,
                "status": inv.status.value,
                "started_at": inv.started_at.astimezone(UTC).isoformat(),
                "completed_at": (
                    inv.completed_at.astimezone(UTC).isoformat()
                    if inv.completed_at is not None
                    else None
                ),
            }
            for inv in invocations
        ]
        package["execution"] = {
            "workflow_id": workflow_id,
            "state": state.value,
            "state_version": workflow.state_version,
            "revision_count": workflow.revision_count,
            "created_at": workflow.created_at.astimezone(UTC).isoformat(),
            "updated_at": workflow.updated_at.astimezone(UTC).isoformat(),
            "transition_count": len(transitions),
            "failure_reason": workflow.failure_reason,
            "invocations": invocation_summaries,
        }

        is_complete = state == WorkflowState.APPROVED
        failure_reason: str | None = None
        if state in TERMINAL_STATES and state != WorkflowState.APPROVED:
            is_complete = False
            failure_reason = workflow.failure_reason or state.value.lower()

        return WorkflowOutput(
            workflow_id=workflow_id,
            state=state,
            package=package,
            is_complete=is_complete,
            failure_reason=failure_reason,
        )

    def assemble_timeline(self, *, workflow_id: str) -> WorkflowTimeline:
        transitions = self._workflow_repo.list_transitions(workflow_id)
        list_tasks = getattr(self._workflow_repo, "list_tasks_for_workflow", None)
        tasks = list_tasks(workflow_id) if callable(list_tasks) else ()
        invocations = self._artifact_repo.list_ai_invocations(workflow_id)

        events: list[TimelineEvent] = []
        for row in transitions:
            events.append(
                TimelineEvent(
                    occurred_at=row.occurred_at,
                    event_type="transition",
                    summary=(
                        f"{row.from_state.value} → {row.to_state.value}: {row.reason}"
                    ),
                    attributes={"stable_id": row.transition_id},
                )
            )
        for row in tasks:
            events.append(
                TimelineEvent(
                    occurred_at=row.created_at,
                    event_type="task_enqueued",
                    summary=f"{row.task_type.value} attempt {row.attempt}",
                    attributes={"stable_id": row.task_id},
                )
            )
        for row in invocations:
            events.append(
                TimelineEvent(
                    occurred_at=row.started_at,
                    event_type="ai_invocation",
                    summary=f"{row.agent_name} {row.status.value}",
                    attributes={"stable_id": row.invocation_id},
                )
            )

        def sort_key(event: TimelineEvent) -> tuple[object, ...]:
            rank = _EVENT_TYPE_RANK.get(event.event_type, 99)
            stable_id = event.attributes.get("stable_id", "")
            return (event.occurred_at, rank, stable_id)

        events.sort(key=sort_key)
        return WorkflowTimeline(workflow_id=workflow_id, events=tuple(events))
