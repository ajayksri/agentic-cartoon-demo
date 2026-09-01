"""Pre-code test mold for WKR-010 — HandlerSupport (LLD §4.11)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents import AgentOutputValidationError
from config.types import AgentId, InjectionId, ProviderId, TaskType

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def _execution_context(*, txn_active: bool = True) -> SimpleNamespace:
    artifact_repo = MagicMock()
    artifact_repo.get_active_artifact.return_value = None
    txn = MagicMock()
    txn.is_in_transaction.return_value = txn_active
    failure_injection = MagicMock()
    failure_injection.invoke_if_active.return_value = True
    provider = SimpleNamespace(provider_id=ProviderId.FAKE)
    return SimpleNamespace(
        config=SimpleNamespace(
            get_agent_config=lambda _aid: SimpleNamespace(model="fake-model"),
        ),
        delivery=SimpleNamespace(
            message=SimpleNamespace(
                workflow_id="wf-hs-1",
                task_id="task-hs-1",
                attempt=1,
                task_type=TaskType.SELECT_TOPIC,
            ),
        ),
        workflow_repo=MagicMock(),
        artifact_repo=artifact_repo,
        transaction_manager=txn,
        failure_injection=failure_injection,
        model_provider_factory=lambda _aid: provider,
        logger=MagicMock(),
        meter=MagicMock(),
        tracer=MagicMock(),
    )


def test_create_artifact_sets_schema_version_in_transaction() -> None:
    """LLD §4.11: content[ARTIFACT_SCHEMA_VERSION]=ARTIFACT_SCHEMA_V1 inside txn."""
    from worker.constants import ARTIFACT_SCHEMA_V1, ARTIFACT_SCHEMA_VERSION
    from worker.handlers.base import HandlerSupport
    from persistence.types import ArtifactType

    context = _execution_context()
    context.artifact_repo.create_artifact.return_value = "art-new-1"
    artifact_id = HandlerSupport.create_artifact(
        context=context,  # type: ignore[arg-type]
        artifact_type=ArtifactType.COLLECTED_STORIES,
        content={"stories": []},
        logical_version=1,
    )
    assert artifact_id == "art-new-1"
    call_spec = context.artifact_repo.create_artifact.call_args.args[0]
    assert call_spec.content[ARTIFACT_SCHEMA_VERSION] == ARTIFACT_SCHEMA_V1


def test_load_active_artifact_json_missing_raises_permanent() -> None:
    from worker import TaskExecutionError
    from worker.handlers.base import HandlerSupport
    from persistence.types import ArtifactType

    context = _execution_context()
    with pytest.raises(TaskExecutionError):
        HandlerSupport.load_active_artifact_json(
            context=context,  # type: ignore[arg-type]
            artifact_type=ArtifactType.COLLECTED_STORIES,
        )


@pytest.mark.wkr_tc("034")
def test_run_agent_stage_invokes_finj_post_agent_before_return() -> None:
    """WKR-TC-034 handler seam: FINJ-WKR-POST-AGENT after agent, before persist."""
    from worker.handlers.base import HandlerSupport

    context = _execution_context()
    invocation_order: list[str] = []

    def agent_call() -> str:
        invocation_order.append("agent")
        return "output"

    HandlerSupport.run_agent_stage(
        context=context,  # type: ignore[arg-type]
        agent_id=AgentId.TOPIC_SELECTOR,
        started_at=_FIXED_NOW,
        input_artifact_id="art-in-1",
        agent_call=agent_call,
        map_audit_status=lambda _err: None,  # type: ignore[arg-type]
    )
    context.failure_injection.invoke_if_active.assert_called_with(InjectionId.FINJ_WKR_POST_AGENT)
    assert invocation_order == ["agent"]


@pytest.mark.wkr_tc("024")
def test_run_agent_stage_failure_appends_audit_then_reraises() -> None:
    """WKR-TC-024: AgentOutputValidationError appended then re-raised."""
    from worker.handlers.base import HandlerSupport

    context = _execution_context()

    def agent_call() -> None:
        raise AgentOutputValidationError("bad output", agent_id=AgentId.TOPIC_SELECTOR)

    with pytest.raises(AgentOutputValidationError):
        HandlerSupport.run_agent_stage(
            context=context,  # type: ignore[arg-type]
            agent_id=AgentId.TOPIC_SELECTOR,
            started_at=_FIXED_NOW,
            input_artifact_id="art-in-1",
            agent_call=agent_call,
            map_audit_status=lambda err: "VALIDATION_FAILED",  # type: ignore[arg-type]
        )
    context.artifact_repo.append_ai_invocation.assert_called_once()


def test_map_story_records_to_candidates_omits_hn_raw_fields() -> None:
    """CG-AGT-002: CandidateStory mapping omits HN raw fields."""
    from worker.handlers.base import HandlerSupport

    content = {
        "candidates": [
            {
                "source_id": "hn-1",
                "title": "Rust async",
                "url": "https://news.ycombinator.com/item?id=1",
                "score": 100,
                "comment_count": 42,
                "raw_hn_payload": {"should": "not appear"},
            }
        ]
    }
    candidates = HandlerSupport.map_story_records_to_candidates(content)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_id == "hn-1"
    assert not hasattr(candidate, "raw_hn_payload")
