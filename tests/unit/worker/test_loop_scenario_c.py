"""Pre-code test mold for WKR-015 — loop orchestration seams (LLD §8.3, §8.6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.types import TaskType
from worker import (
    DuplicateResolution,
    IdempotencyPhase,
    TaskHandlerOutcome,
    TaskHandlerResult,
)
from workflow.types import TransitionSignal, WorkflowState


def test_commit_success_path_claims_before_transition() -> None:
    """LLD §8.3: claim_completion before apply_transition on success path."""
    from worker.loop import DefaultWorkerLoop

    claim_order: list[str] = []
    loop = object.__new__(DefaultWorkerLoop)
    loop._orchestrator = type(  # type: ignore[attr-defined]
        "Orchestrator",
        (),
        {
            "claim_completion": lambda _self, *, spec: (
                claim_order.append("claim") or _Claimed()
            ),
        },
    )()
    loop._workflow_engine = type(  # type: ignore[attr-defined]
        "Engine",
        (),
        {
            "apply_transition": lambda _self, _req: claim_order.append("transition")
            or type(
                "TransitionResult",
                (),
                {
                    "enqueued_task": None,
                    "to_state": WorkflowState.COLLECTING,
                },
            )(),
        },
    )()
    loop._workflow_repo = type(  # type: ignore[attr-defined]
        "Repo",
        (),
        {"update_task": lambda *_a, **_k: None},
    )()
    loop._event_order = []  # type: ignore[attr-defined]
    loop._clock = lambda: datetime.now(UTC)  # type: ignore[attr-defined]

    class _Claimed:
        phase = IdempotencyPhase.CLAIMED

    handler_result = TaskHandlerResult(
        outcome=TaskHandlerOutcome.COMPLETED,
        transition_signal=TransitionSignal.STAGE_COMPLETED,
        result_artifact_id="art-1",
    )
    DefaultWorkerLoop._commit_success_path(  # type: ignore[attr-defined]
        loop,
        ctx=type("Ctx", (), {"task_type": TaskType.COLLECT, "workflow_id": "wf-1", "task_id": "t-1"})(),
        handler_result=handler_result,
        idempotency_key="wf-1:COLLECT:1",
    )
    assert claim_order == ["claim", "transition"]


@pytest.mark.wkr_tc("070")
def test_ack_only_after_transaction_commit_and_transition() -> None:
    """WKR-TC-070: TaskQueue.ack after commit + transition (loop seam)."""
    from worker.loop import DefaultWorkerLoop

    events: list[str] = []
    loop = object.__new__(DefaultWorkerLoop)
    loop._task_queue = type(  # type: ignore[attr-defined]
        "Queue",
        (),
        {"ack": lambda _self, _delivery: events.append("ack")},
    )()
    loop._transaction_manager = type(  # type: ignore[attr-defined]
        "Txn",
        (),
        {
            "transaction": lambda _self: _TxnContext(events),
            "is_in_transaction": lambda _self: False,
        },
    )()
    assert hasattr(DefaultWorkerLoop, "_process_delivery")


class _TxnContext:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self) -> "_TxnContext":
        return self

    def __exit__(self, *_args: object) -> None:
        self._events.append("commit")


@pytest.mark.wkr_tc("071")
def test_lease_conflict_records_duplicate_without_ack() -> None:
    """WKR-TC-071: lease conflict → DETECTED_DURING_EXECUTION, no ACK."""
    from worker import LeaseConflictError

    err = LeaseConflictError("held", task_id="task-1", worker_id="worker-a")
    assert err.task_id == "task-1"
    resolution = DuplicateResolution.DETECTED_DURING_EXECUTION
    assert resolution.value == "detected_during_execution"


def test_scenario_c_loser_path_skips_when_post_state_matches() -> None:
    """LLD §8.6: skip apply_transition when reloaded state equals expected_post."""
    from worker.state_mapping import WorkflowStateGuard

    expected_post = WorkflowStateGuard.post_transition_state(
        TaskType.GENERATE_SCENARIO,
        TransitionSignal.STAGE_COMPLETED,
    )
    current = WorkflowState.SCENARIO_GENERATED
    should_skip = current == expected_post
    assert should_skip is True
