"""SELECT_TOPIC stage handler (LLD §4.12)."""

from __future__ import annotations

from datetime import UTC, datetime

from agents.types import TopicSelectionInput, TopicSelectionOutcome
from config.types import AgentId, TaskType
from persistence.types import ArtifactType, InvocationStatus
from workflow.types import TransitionSignal

from ..context import AgentRunContextBuilder
from .base import AiInvocationDraft, HandlerSupport
from ..types import TaskExecutionContext, TaskHandlerOutcome, TaskHandlerResult


class SelectTopicTaskHandler:
    """Runs topic selection agent and persists TOPIC_SELECTION artifact."""

    @property
    def task_type(self) -> TaskType:
        return TaskType.SELECT_TOPIC

    def handle(self, context: TaskExecutionContext) -> TaskHandlerResult:
        collected_record, _content = HandlerSupport.load_active_artifact_json(
            context,
            ArtifactType.COLLECTED_STORIES,
        )
        candidates = HandlerSupport.map_story_records_to_candidates(_content)
        agent_context = AgentRunContextBuilder.build(
            agent_id=AgentId.TOPIC_SELECTOR,
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
            agent_id=AgentId.TOPIC_SELECTOR,
            started_at=started_at,
            input_artifact_id=collected_record.artifact_id,
            agent_call=lambda: context.topic_selection_agent.run(
                context=agent_context,
                input=TopicSelectionInput(candidates=candidates),
            ),
            map_audit_status=HandlerSupport.map_agent_error_to_invocation_status,
        )
        topic_content = _serialize_topic_output(output)
        artifact_id = HandlerSupport.create_artifact(
            context=context,
            artifact_type=ArtifactType.TOPIC_SELECTION,
            content=topic_content,
            logical_version=1,
        )
        agent_config = context.config.get_agent_config(AgentId.TOPIC_SELECTOR)
        success_draft = AiInvocationDraft(
            agent_name="topic_selector",
            agent_version="1",
            prompt_version=getattr(output, "prompt_version", "unknown"),
            provider=agent_context.provider.provider_id.value,
            model=agent_config.model,
            input_artifact_id=collected_record.artifact_id,
            output_artifact_id=artifact_id,
            attempt=context.delivery.message.attempt,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status=InvocationStatus.SUCCESS,
        )
        HandlerSupport.append_ai_invocation(context, success_draft)
        signal = (
            TransitionSignal.STAGE_COMPLETED
            if getattr(output, "outcome", None) == TopicSelectionOutcome.TOPIC_SELECTED
            else TransitionSignal.NO_SUITABLE_TOPIC
        )
        return TaskHandlerResult(
            outcome=TaskHandlerOutcome.COMPLETED,
            transition_signal=signal,
            result_artifact_id=artifact_id,
        )


def _serialize_topic_output(output: object) -> dict[str, object]:
    outcome = getattr(output, "outcome", None)
    outcome_value = outcome.value if outcome is not None else "no_suitable_topic"
    scores = getattr(output, "scores", None)
    scores_dict: dict[str, float] | None = None
    if scores is not None:
        scores_dict = {
            "technical_relevance": float(scores.technical_relevance),
            "developer_relevance": float(scores.developer_relevance),
            "discussion_interest": float(scores.discussion_interest),
            "humour_potential": float(scores.humour_potential),
            "irony_contradiction": float(scores.irony_contradiction),
            "visual_scenario_potential": float(scores.visual_scenario_potential),
            "background_knowledge_required": float(scores.background_knowledge_required),
        }
    alternatives = [
        {"topic": alt.topic, "reason": alt.rationale}
        for alt in getattr(output, "alternatives", ())
    ]
    return {
        "outcome": outcome_value,
        "selected_topic": getattr(output, "selected_topic", None),
        "why_interesting": getattr(output, "why_interesting", None),
        "cartoon_angle": getattr(output, "cartoon_angle", None),
        "scores": scores_dict,
        "alternatives": alternatives,
        "prompt_version": getattr(output, "prompt_version", "unknown"),
    }
