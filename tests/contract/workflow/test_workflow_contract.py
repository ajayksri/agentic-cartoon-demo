"""Contract tests WF-TC-001 through WF-TC-026 (WF-014).

Imports ONLY from the workflow package public surface (`workflow.__init__`).
Boundary imports for fixture injection live in helpers.py / conftest.py per LLD §14.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from config.types import TaskType
from workflow import (
    ApprovalAction,
    InvalidApprovalActionError,
    InvalidTransitionError,
    TERMINAL_WORKFLOW_STATES,
    TransitionRequest,
    TransitionSignal,
    WorkflowConflictError,
    WorkflowEngine,
    WorkflowNotFoundError,
    WorkflowState,
    WorkflowTerminalError,
    create_workflow_engine,
)

from .helpers import (
    approval_with_txn,
    initiate_with_txn,
    memory_workflow_engine,
    memory_workflow_fixture,
    minimal_workflow_config,
    pending_outbox_for_workflow,
    seed_output_package_artifacts,
    seed_timeline_collision_fixture,
    seed_workflow_awaiting_human_approval,
    stage_completed_request,
    timeline_sort_key,
    transition_with_txn,
)

pytestmark = []

_FORBIDDEN_IMPORT_PREFIXES = (
    "worker",
    "agents",
    "api",
    "task_queue",
    "providers",
    "collector",
)


@pytest.mark.wf_tc("001")
def test_wf_tc_001_initiate_creates_collecting_with_collect_outbox() -> None:
    """WF-TC-001: initiate_workflow → COLLECTING + COLLECT outbox fields."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = initiate_with_txn(engine, txn, config=config)

    assert result.state == WorkflowState.COLLECTING
    assert result.workflow_id
    assert result.enqueued_task is not None
    assert result.enqueued_task.task_type == TaskType.COLLECT
    assert result.enqueued_task.idempotency_key.endswith(":COLLECT:1")


@pytest.mark.wf_tc("002")
def test_wf_tc_002_initiation_appends_canonical_transition_history() -> None:
    """WF-TC-002: History shows exactly one transition CREATED → COLLECTING."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    initiated = initiate_with_txn(engine, txn, config=config)
    history = engine.get_workflow_history(initiated.workflow_id)

    assert len(history.transitions) == 1
    transition = history.transitions[0]
    assert transition.from_state == WorkflowState.CREATED
    assert transition.to_state == WorkflowState.COLLECTING
    assert transition.reason == "workflow_initiated"


@pytest.mark.wf_tc("003")
def test_wf_tc_003_valid_stage_completion_advances_state() -> None:
    """WF-TC-003: COLLECTING + STAGE_COMPLETED → COLLECTED."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)
    initiated = initiate_with_txn(engine, txn, config=config)

    result = transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id=initiated.workflow_id,
            expected_state=WorkflowState.COLLECTING,
        ),
    )

    assert result.to_state == WorkflowState.COLLECTED


@pytest.mark.wf_tc("004")
def test_wf_tc_004_forward_transition_enqueues_select_topic_outbox() -> None:
    """WF-TC-004: COLLECTED + STAGE_COMPLETED enqueues SELECT_TOPIC outbox."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)
    initiated = initiate_with_txn(engine, txn, config=config)
    collect_result = transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id=initiated.workflow_id,
            expected_state=WorkflowState.COLLECTING,
        ),
    )

    result = transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id=initiated.workflow_id,
            expected_state=WorkflowState.COLLECTED,
        ),
    )

    assert collect_result.outbox_written is True
    assert collect_result.enqueued_task is not None
    assert collect_result.enqueued_task.task_type == TaskType.SELECT_TOPIC
    assert result.to_state == WorkflowState.SELECTING_TOPIC


@pytest.mark.wf_tc("005")
def test_wf_tc_005_terminal_approved_rejects_transition() -> None:
    """WF-TC-005: APPROVED + STAGE_COMPLETED → InvalidTransitionError."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    with pytest.raises(InvalidTransitionError):
        transition_with_txn(
            engine,
            txn,
            stage_completed_request(
                workflow_id="wf-terminal-approved",
                expected_state=WorkflowState.APPROVED,
            ),
        )


@pytest.mark.wf_tc("006")
def test_wf_tc_006_stale_expected_state_raises_conflict() -> None:
    """WF-TC-006: Stale expected_state → WorkflowConflictError."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)
    initiated = initiate_with_txn(engine, txn, config=config)

    with pytest.raises(WorkflowConflictError):
        transition_with_txn(
            engine,
            txn,
            stage_completed_request(
                workflow_id=initiated.workflow_id,
                expected_state=WorkflowState.SELECTING_TOPIC,
            ),
        )


@pytest.mark.wf_tc("007")
def test_wf_tc_007_no_suitable_topic_terminal_branch() -> None:
    """WF-TC-007: SELECTING_TOPIC + NO_SUITABLE_TOPIC → NO_SUITABLE_TOPIC terminal."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-no-topic",
            expected_state=WorkflowState.SELECTING_TOPIC,
            signal=TransitionSignal.NO_SUITABLE_TOPIC,
            reason="no_suitable_topic",
        ),
    )

    assert result.to_state == WorkflowState.NO_SUITABLE_TOPIC
    assert result.outbox_written is False


@pytest.mark.wf_tc("008")
def test_wf_tc_008_unrecoverable_error_to_failed() -> None:
    """WF-TC-008: GENERATING_SCENARIO + UNRECOVERABLE_ERROR → FAILED."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-unrecoverable",
            expected_state=WorkflowState.GENERATING_SCENARIO,
            signal=TransitionSignal.UNRECOVERABLE_ERROR,
            reason="provider_failure",
        ),
    )

    assert result.to_state == WorkflowState.FAILED
    assert result.outbox_written is False


@pytest.mark.wf_tc("009")
def test_wf_tc_009_retries_exhausted_to_failed_permanently() -> None:
    """WF-TC-009: REVIEWING + RETRIES_EXHAUSTED → FAILED_PERMANENTLY."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-retries-exhausted",
            expected_state=WorkflowState.REVIEWING,
            signal=TransitionSignal.RETRIES_EXHAUSTED,
            reason="max_retries",
        ),
    )

    assert result.to_state == WorkflowState.FAILED_PERMANENTLY


@pytest.mark.wf_tc("010")
def test_wf_tc_010_critic_pass_reaches_awaiting_human_approval() -> None:
    """WF-TC-010: CRITIC_PASS + STAGE_COMPLETED → AWAITING_HUMAN_APPROVAL."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-critic-pass",
            expected_state=WorkflowState.REVIEWING,
            signal=TransitionSignal.CRITIC_PASS,
            reason="critic_passed",
        ),
    )
    result = transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id="wf-critic-pass",
            expected_state=WorkflowState.REVIEW_PASSED,
        ),
    )

    assert result.to_state == WorkflowState.AWAITING_HUMAN_APPROVAL


@pytest.mark.wf_tc("011")
def test_wf_tc_011_approval_wait_has_no_pending_outbox() -> None:
    """WF-TC-011: AWAITING_HUMAN_APPROVAL has no pending outbox tasks."""
    config = minimal_workflow_config()
    fixture = memory_workflow_fixture(config=config)
    workflow_id = "wf-awaiting-approval"

    seed_workflow_awaiting_human_approval(fixture.engine, fixture.txn, workflow_id=workflow_id)

    status = fixture.engine.get_workflow_status(workflow_id)
    pending = pending_outbox_for_workflow(fixture.outbox_repo, workflow_id)

    assert status.state == WorkflowState.AWAITING_HUMAN_APPROVAL
    assert pending == []


@pytest.mark.wf_tc("012")
def test_wf_tc_012_approve_transitions_to_terminal_approved() -> None:
    """WF-TC-012: APPROVE → APPROVED with no outbox."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = approval_with_txn(
        engine,
        txn,
        workflow_id="wf-approve",
        action=ApprovalAction.APPROVE,
    )

    assert result.to_state == WorkflowState.APPROVED
    assert result.enqueued_task is None


@pytest.mark.wf_tc("013")
def test_wf_tc_013_request_regeneration_enqueues_generate_scenario() -> None:
    """WF-TC-013: REQUEST_REGENERATION enqueues GENERATE_SCENARIO with bumped logical version."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    result = approval_with_txn(
        engine,
        txn,
        workflow_id="wf-regenerate",
        action=ApprovalAction.REQUEST_REGENERATION,
    )

    assert result.to_state == WorkflowState.GENERATING_SCENARIO
    assert result.enqueued_task is not None
    assert result.enqueued_task.task_type == TaskType.GENERATE_SCENARIO
    assert ":GENERATE_SCENARIO:" in result.enqueued_task.idempotency_key


@pytest.mark.wf_tc("014")
def test_wf_tc_014_approval_from_wrong_state_rejected() -> None:
    """WF-TC-014: Approval from COLLECTING → InvalidApprovalActionError."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)
    initiated = initiate_with_txn(engine, txn, config=config)

    with pytest.raises(InvalidApprovalActionError):
        approval_with_txn(
            engine,
            txn,
            workflow_id=initiated.workflow_id,
            action=ApprovalAction.APPROVE,
        )


@pytest.mark.wf_tc("015")
def test_wf_tc_015_duplicate_approval_on_terminal_rejected() -> None:
    """WF-TC-015: Duplicate approval on APPROVED → InvalidApprovalActionError or WorkflowTerminalError."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    with pytest.raises((InvalidApprovalActionError, WorkflowTerminalError)):
        approval_with_txn(
            engine,
            txn,
            workflow_id="wf-already-approved",
            action=ApprovalAction.REJECT,
        )


@pytest.mark.wf_tc("016")
def test_wf_tc_016_critic_revise_loop_enqueues_regeneration() -> None:
    """WF-TC-016: CRITIC_REVISE → REVISION_REQUIRED with GENERATE_SCENARIO outbox on completion."""
    config = minimal_workflow_config(max_scenario_revisions=3)
    engine, txn = memory_workflow_engine(config=config)

    revise_result = transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-revise-loop",
            expected_state=WorkflowState.REVIEWING,
            signal=TransitionSignal.CRITIC_REVISE,
            reason="critic_revise",
        ),
    )

    assert revise_result.to_state == WorkflowState.REVISION_REQUIRED

    complete_result = transition_with_txn(
        engine,
        txn,
        stage_completed_request(
            workflow_id="wf-revise-loop",
            expected_state=WorkflowState.REVISION_REQUIRED,
        ),
    )

    assert complete_result.to_state == WorkflowState.GENERATING_SCENARIO
    assert complete_result.enqueued_task is not None
    assert complete_result.enqueued_task.task_type == TaskType.GENERATE_SCENARIO


@pytest.mark.wf_tc("017")
def test_wf_tc_017_max_revisions_triggers_review_failed() -> None:
    """WF-TC-017: revision_count at max → CRITIC_REVISE routes to REVIEW_FAILED."""
    config = minimal_workflow_config(max_scenario_revisions=2)
    engine, txn = memory_workflow_engine(config=config)

    result = transition_with_txn(
        engine,
        txn,
        TransitionRequest(
            workflow_id="wf-max-revisions",
            expected_state=WorkflowState.REVIEWING,
            signal=TransitionSignal.CRITIC_REVISE,
            reason="critic_revise",
        ),
    )

    assert result.to_state == WorkflowState.REVIEW_FAILED


@pytest.mark.wf_tc("018")
def test_wf_tc_018_reconcile_repairs_missing_outbox_rp001() -> None:
    """WF-TC-018: COLLECTED without outbox → RP-001 repair via reconcile_stuck_workflows."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    with txn.transaction():  # type: ignore[attr-defined]
        result = engine.reconcile_stuck_workflows(config=config)

    assert result.repaired_count >= 1


@pytest.mark.wf_tc("019")
def test_wf_tc_019_reconciliation_is_idempotent() -> None:
    """WF-TC-019: Second reconcile immediately → repaired=False, no duplicate outbox."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    with txn.transaction():  # type: ignore[attr-defined]
        first = engine.reconcile_stuck_workflows(config=config)
    with txn.transaction():  # type: ignore[attr-defined]
        second = engine.reconcile_stuck_workflows(config=config)

    assert second.repaired_count == 0
    assert all(not report.repaired for report in second.reports)


@pytest.mark.wf_tc("020")
def test_wf_tc_020_output_package_aggregates_artifacts() -> None:
    """WF-TC-020: get_workflow_output package contains topic, scenario, critic, execution keys."""
    config = minimal_workflow_config()
    fixture = memory_workflow_fixture(config=config)
    workflow_id = "wf-output-complete"

    seed_output_package_artifacts(fixture.artifact_repo, workflow_id=workflow_id)

    output = fixture.engine.get_workflow_output(workflow_id)

    assert output.is_complete is True
    assert "topic" in output.package
    assert "scenario" in output.package
    assert "critic" in output.package
    assert "execution" in output.package
    assert output.package["topic"]
    assert output.package["scenario"]
    assert output.package["critic"]
    assert output.package["execution"]


@pytest.mark.wf_tc("021")
def test_wf_tc_021_partial_output_on_terminal_failure() -> None:
    """WF-TC-021: FAILED with partial artifacts → is_complete=False, failure_reason set."""
    config = minimal_workflow_config()
    engine, _txn = memory_workflow_engine(config=config)

    output = engine.get_workflow_output("wf-output-failed")

    assert output.is_complete is False
    assert output.failure_reason is not None


@pytest.mark.wf_tc("022")
def test_wf_tc_022_timeline_ordered_by_occurred_at_and_event_type_rank() -> None:
    """WF-TC-022: Timeline strictly ordered; ties broken by event_type_rank then stable id."""
    config = minimal_workflow_config()
    fixture = memory_workflow_fixture(config=config)
    workflow_id = "wf-timeline-ordering"

    seed_timeline_collision_fixture(
        fixture.workflow_repo,
        fixture.artifact_repo,
        workflow_id=workflow_id,
    )

    timeline = fixture.engine.get_workflow_timeline(workflow_id)

    assert timeline.events
    sort_keys = [timeline_sort_key(event) for event in timeline.events]
    assert sort_keys == sorted(sort_keys)

    collision_ts = timeline.events[0].occurred_at
    colliding = [event for event in timeline.events if event.occurred_at == collision_ts]
    assert len(colliding) >= 3
    assert colliding == sorted(colliding, key=timeline_sort_key)


@pytest.mark.wf_tc("023")
def test_wf_tc_023_read_models_do_not_mutate_state() -> None:
    """WF-TC-023: Read APIs leave get_workflow_status snapshot unchanged."""
    config = minimal_workflow_config()
    engine, _txn = memory_workflow_engine(config=config)
    workflow_id = "wf-read-only"

    before = engine.get_workflow_status(workflow_id)
    engine.get_workflow_history(workflow_id)
    engine.get_workflow_output(workflow_id)
    engine.get_workflow_timeline(workflow_id)
    after = engine.get_workflow_status(workflow_id)

    assert after.state == before.state
    assert after.state_version == before.state_version


@pytest.mark.wf_tc("024")
def test_wf_tc_024_unknown_workflow_raises_not_found() -> None:
    """WF-TC-024: Unknown workflow_id → WorkflowNotFoundError."""
    config = minimal_workflow_config()
    engine, txn = memory_workflow_engine(config=config)

    with pytest.raises(WorkflowNotFoundError):
        engine.get_workflow_status("wf-does-not-exist")

    with pytest.raises(WorkflowNotFoundError):
        transition_with_txn(
            engine,
            txn,
            stage_completed_request(
                workflow_id="wf-does-not-exist",
                expected_state=WorkflowState.COLLECTING,
            ),
        )


@pytest.mark.wf_tc("025")
def test_wf_tc_025_no_forbidden_imports_in_workflow_package() -> None:
    """WF-TC-025: Static import analysis — no forbidden module imports."""
    workflow_src = Path(__file__).resolve().parents[3] / "src" / "workflow"
    violations: list[str] = []

    for py_file in workflow_src.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in _FORBIDDEN_IMPORT_PREFIXES:
                        violations.append(f"{py_file.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in _FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(f"{py_file.name}: from {node.module}")

    assert violations == []


@pytest.mark.wf_tc("026")
def test_wf_tc_026_public_exports_match_interfaces() -> None:
    """WF-TC-026: WorkflowState has 17 members; WorkflowEngine defines all protocol operations."""
    assert len(WorkflowState) == 17
    assert TERMINAL_WORKFLOW_STATES

    expected_ops = {
        "initiate_workflow",
        "apply_transition",
        "apply_approval_action",
        "reconcile_stuck_workflows",
        "get_workflow_status",
        "get_workflow_history",
        "get_workflow_output",
        "get_workflow_timeline",
    }
    for op in expected_ops:
        assert hasattr(WorkflowEngine, op)

    assert callable(create_workflow_engine)
    assert "config" in inspect.signature(create_workflow_engine).parameters
