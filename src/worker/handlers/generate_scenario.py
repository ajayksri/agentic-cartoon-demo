"""GENERATE_SCENARIO stage handler (LLD §4.12)."""

from __future__ import annotations

from datetime import UTC, datetime

from agents.types import ScenarioGenerationInput, TopicSelectionOutput
from config.types import AgentId, TaskType
from persistence.types import ArtifactType, InvocationStatus
from workflow.types import TransitionSignal

from ..context import AgentRunContextBuilder
from ..errors import TaskExecutionError
from .base import AiInvocationDraft, HandlerSupport
from ..messages import execution_error_message
from ..idempotency import resolve_logical_version
from ..types import TaskExecutionContext, TaskHandlerOutcome, TaskHandlerResult


class GenerateScenarioTaskHandler:
    """Runs scenario generation agent and persists SCENARIO artifact."""

    @property
    def task_type(self) -> TaskType:
        return TaskType.GENERATE_SCENARIO

    def handle(self, context: TaskExecutionContext) -> TaskHandlerResult:
        topic_record, topic_content = HandlerSupport.load_active_artifact_json(
            context,
            ArtifactType.TOPIC_SELECTION,
        )
        if topic_content.get("outcome") != "topic_selected":
            raise TaskExecutionError(
                execution_error_message(
                    workflow_id=context.delivery.message.workflow_id,
                    task_id=context.delivery.message.task_id,
                    task_type=self.task_type,
                    detail="TOPIC_SELECTION prerequisite not satisfied",
                ),
                workflow_id=context.delivery.message.workflow_id,
                task_id=context.delivery.message.task_id,
                task_type=self.task_type,
                retryable=False,
            )
        topic_output = _topic_output_from_content(topic_content)
        agent_context = AgentRunContextBuilder.build(
            agent_id=AgentId.SCENARIO_GENERATOR,
            delivery=context.delivery,
            config=context.config,
            model_provider_factory=context.model_provider_factory,
            logger=context.logger,
            meter=context.meter,
            tracer=context.tracer,
            attempt=context.delivery.message.attempt,
        )
        started_at = datetime.now(UTC)
        output, _ = HandlerSupport.run_agent_stage(
            context=context,
            agent_id=AgentId.SCENARIO_GENERATOR,
            started_at=started_at,
            input_artifact_id=topic_record.artifact_id,
            agent_call=lambda: context.scenario_generation_agent.run(
                context=agent_context,
                input=ScenarioGenerationInput(topic=topic_output),
            ),
            map_audit_status=HandlerSupport.map_agent_error_to_invocation_status,
        )
        logical_version = resolve_logical_version(
            task_type=self.task_type,
            task_record=context.task_record,
            delivery=context.delivery,
            artifact_repo=context.artifact_repo,
            workflow_repo=context.workflow_repo,
        )
        scenario_content = _serialize_scenario_output(
            output,
            logical_version,
            topic_content,
        )
        artifact_id = HandlerSupport.create_artifact(
            context=context,
            artifact_type=ArtifactType.SCENARIO,
            content=scenario_content,
            logical_version=logical_version,
        )
        agent_config = context.config.get_agent_config(AgentId.SCENARIO_GENERATOR)
        success_draft = AiInvocationDraft(
            agent_name="scenario_generator",
            agent_version="1",
            prompt_version=getattr(output, "prompt_version", "unknown"),
            provider=agent_context.provider.provider_id.value,
            model=agent_config.model,
            input_artifact_id=topic_record.artifact_id,
            output_artifact_id=artifact_id,
            attempt=context.delivery.message.attempt,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status=InvocationStatus.SUCCESS,
        )
        HandlerSupport.append_ai_invocation(context, success_draft)
        return TaskHandlerResult(
            outcome=TaskHandlerOutcome.COMPLETED,
            transition_signal=TransitionSignal.STAGE_COMPLETED,
            result_artifact_id=artifact_id,
        )


def _topic_output_from_content(content: dict[str, object]) -> TopicSelectionOutput:
    from agents.types import TopicSelectionOutcome

    outcome = TopicSelectionOutcome(str(content.get("outcome", "no_suitable_topic")))
    return TopicSelectionOutput(
        outcome=outcome,
        prompt_version=str(content.get("prompt_version", "unknown")),
        selected_topic=content.get("selected_topic") if content.get("selected_topic") else None,
        why_interesting=content.get("why_interesting") if content.get("why_interesting") else None,
        cartoon_angle=content.get("cartoon_angle") if content.get("cartoon_angle") else None,
    )


def _serialize_scenario_output(
    output: object,
    logical_version: int,
    topic_content: dict[str, object],
) -> dict[str, object]:
    panels = [
        {
            "caption": getattr(panel, "scene", ""),
            "dialogue": getattr(panel, "dialogue", None),
        }
        for panel in getattr(output, "panels", ())
    ]
    selected_topic = getattr(output, "topic", None) or topic_content.get("selected_topic") or ""
    return {
        "logical_version": logical_version,
        "topic": {
            "selected_topic": selected_topic,
            "why_interesting": topic_content.get("why_interesting") or "",
            "cartoon_angle": topic_content.get("cartoon_angle") or "",
        },
        "premise": getattr(output, "premise", ""),
        "characters": [
            {"name": name, "role": "character"} for name in getattr(output, "characters", ())
        ],
        "panels": panels,
        "punchline": getattr(output, "punchline", "") or "",
        "prompt_version": getattr(output, "prompt_version", "unknown"),
    }
