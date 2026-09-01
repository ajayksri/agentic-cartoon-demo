"""COLLECT stage handler (LLD §4.12)."""

from __future__ import annotations

from datetime import UTC, datetime

from config.types import TaskType
from persistence.types import ArtifactType
from workflow.types import TransitionSignal

from .base import HandlerSupport
from ..types import TaskExecutionContext, TaskHandlerOutcome, TaskHandlerResult


class CollectTaskHandler:
    """Executes collector stage and persists COLLECTED_STORIES artifact."""

    @property
    def task_type(self) -> TaskType:
        return TaskType.COLLECT

    def handle(self, context: TaskExecutionContext) -> TaskHandlerResult:
        result = context.collector.collect_stories(config=context.config)
        content = _serialize_collection_result(result)
        artifact_id = HandlerSupport.create_artifact(
            context=context,
            artifact_type=ArtifactType.COLLECTED_STORIES,
            content=content,
            logical_version=1,
        )
        return TaskHandlerResult(
            outcome=TaskHandlerOutcome.COMPLETED,
            transition_signal=TransitionSignal.STAGE_COMPLETED,
            result_artifact_id=artifact_id,
        )


def _serialize_collection_result(result: object) -> dict[str, object]:
    stories = [
        _story_snapshot(story) for story in getattr(result, "stories", ())
    ]
    candidates = [
        _story_snapshot(story) for story in getattr(result, "candidates", ())
    ]
    rejected = [
        {
            "source_id": getattr(item, "source_id", ""),
            "reason_code": getattr(getattr(item, "reason_code", None), "value", str(item)),
            "reason_detail": getattr(item, "reason_detail", None),
        }
        for item in getattr(result, "rejected", ())
    ]
    stats = getattr(result, "stats", None)
    stats_dict = {
        "fetched_count": getattr(stats, "fetched_count", 0),
        "accepted_count": getattr(stats, "accepted_count", 0),
        "rejected_count": getattr(stats, "rejected_count", 0),
        "candidate_count": getattr(stats, "candidate_count", 0),
    }
    completed_at = getattr(result, "completed_at", datetime.now(UTC))
    return {
        "collected_at": completed_at.isoformat(),
        "stats": stats_dict,
        "stories": stories,
        "candidates": candidates,
        "rejected": rejected,
    }


def _story_snapshot(story: object) -> dict[str, object]:
    return {
        "source_id": getattr(story, "source_id", ""),
        "title": getattr(story, "title", None),
        "url": getattr(story, "url", None),
        "score": getattr(story, "score", None),
        "comment_count": getattr(story, "comment_count", None),
    }
