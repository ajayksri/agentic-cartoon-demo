"""REVIEW_SCENARIO stage handler (LLD §4.12)."""

# GUARDRAIL: Quality — critic verdict drives REVISE loop or progression toward human approval.

from __future__ import annotations

from datetime import UTC, datetime

from agents.types import CriticInput, CriticStatus, ScenarioOutput, ScenarioPanel
from config.types import AgentId, TaskType
from persistence.types import ArtifactType, InvocationStatus
from workflow.types import TransitionSignal

from ..context import AgentRunContextBuilder
from .base import AiInvocationDraft, HandlerSupport
from ..types import TaskExecutionContext, TaskHandlerOutcome, TaskHandlerResult


class ReviewScenarioTaskHandler:
    """Runs critic agent and persists CRITIC_REVIEW artifact."""

    @property
    def task_type(self) -> TaskType:
        return TaskType.REVIEW_SCENARIO

    def handle(self, context: TaskExecutionContext) -> TaskHandlerResult:
        scenario_record, scenario_content = HandlerSupport.load_active_artifact_json(
            context,
            ArtifactType.SCENARIO,
        )
        workflow = context.workflow_repo.get_workflow(
            context.delivery.message.workflow_id
        )
        revision_number = workflow.revision_count if workflow is not None else 0
        scenario_output = _scenario_output_from_content(scenario_content)
        agent_context = AgentRunContextBuilder.build(
            agent_id=AgentId.CRITIC,
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
            agent_id=AgentId.CRITIC,
            started_at=started_at,
            input_artifact_id=scenario_record.artifact_id,
            agent_call=lambda: context.critic_agent.run(
                context=agent_context,
                input=CriticInput(
                    scenario=scenario_output,
                    revision_number=revision_number,
                ),
            ),
            map_audit_status=HandlerSupport.map_agent_error_to_invocation_status,
        )
        review_content = _serialize_critic_output(output)
        artifact_id = HandlerSupport.create_artifact(
            context=context,
            artifact_type=ArtifactType.CRITIC_REVIEW,
            content=review_content,
            logical_version=1,
        )
        agent_config = context.config.get_agent_config(AgentId.CRITIC)
        success_draft = AiInvocationDraft(
            agent_name="critic",
            agent_version="1",
            prompt_version=getattr(output, "prompt_version", "unknown"),
            provider=agent_context.provider.provider_id.value,
            model=agent_config.model,
            input_artifact_id=scenario_record.artifact_id,
            output_artifact_id=artifact_id,
            attempt=context.delivery.message.attempt,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status=InvocationStatus.SUCCESS,
        )
        HandlerSupport.append_ai_invocation(context, success_draft)
        signal = (
            TransitionSignal.CRITIC_PASS
            if getattr(output, "status", None) == CriticStatus.PASS
            else TransitionSignal.CRITIC_REVISE
        )
        return TaskHandlerResult(
            outcome=TaskHandlerOutcome.COMPLETED,
            transition_signal=signal,
            result_artifact_id=artifact_id,
        )


def _scenario_output_from_content(content: dict[str, object]) -> ScenarioOutput:
    panels_raw = content.get("panels", [])
    panels: list[ScenarioPanel] = []
    if isinstance(panels_raw, list):
        for panel in panels_raw:
            if isinstance(panel, dict):
                panels.append(
                    ScenarioPanel(
                        scene=str(panel.get("caption", "")),
                        dialogue=str(panel.get("dialogue", "")) if panel.get("dialogue") else "",
                    )
                )
    topic = content.get("topic", {})
    topic_str = ""
    if isinstance(topic, dict):
        topic_str = str(topic.get("selected_topic", ""))
    return ScenarioOutput(
        topic=topic_str,
        premise=str(content.get("premise", "")),
        characters=tuple(
            str(c.get("name", ""))
            for c in (content.get("characters", []) if isinstance(content.get("characters"), list) else [])
            if isinstance(c, dict)
        ),
        panels=tuple(panels),
        punchline=str(content.get("punchline", "")) if content.get("punchline") else "",
        prompt_version=str(content.get("prompt_version", "unknown")),
    )


def _serialize_critic_output(output: object) -> dict[str, object]:
    issues = [
        {
            "dimension": getattr(issue.dimension, "value", str(issue.dimension)),
            "description": issue.description,
        }
        for issue in getattr(output, "issues", ())
    ]
    status = getattr(output, "status", CriticStatus.REVISE)
    return {
        "status": status.value if hasattr(status, "value") else str(status),
        "dimensions": {},
        "issues": issues,
        "prompt_version": getattr(output, "prompt_version", "unknown"),
    }
