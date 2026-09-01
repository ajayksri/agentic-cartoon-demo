"""Scenario workflow engine — injectable double until LLD-RT-001 closes.

Simulates fake-provider worker progression (COLLECT → … → AWAITING_HUMAN_APPROVAL)
without importing worker.handlers or agents internals (interface-gaps §4.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from config.types import AppConfig, TaskType
from workflow import (
    ApprovalAction,
    ApprovalActionResult,
    InitiateWorkflowRequest,
    InitiateWorkflowResult,
    OutboxTaskSpec,
    ReconciliationResult,
    TransitionRecord,
    TransitionRequest,
    TransitionResult,
    WorkflowHistory,
    WorkflowNotFoundError,
    WorkflowOutput,
    WorkflowState,
    WorkflowStatus,
    WorkflowTimeline,
)


@dataclass
class _Lease:
    task_id: str
    worker_id: str


@dataclass
class _WorkflowRecord:
    workflow_id: str
    state: WorkflowState
    state_version: int
    created_at: datetime
    updated_at: datetime
    revision_count: int = 0
    failure_reason: str | None = None
    package: dict[str, object] = field(default_factory=dict)
    transitions: list[TransitionRecord] = field(default_factory=list)
    correlation_id: str | None = None
    actor: str | None = None


class ScenarioWorkflowEngine:
    """WorkflowEngine double with injectable fake-provider pipeline + lease tracking."""

    def __init__(self) -> None:
        self._workflows: dict[str, _WorkflowRecord] = {}
        self._leases: list[_Lease] = []
        self.provider_id_used: str = "fake"

    @property
    def active_leases(self) -> tuple[_Lease, ...]:
        """Leases held by the injectable worker simulation (empty during approval wait)."""
        return tuple(self._leases)

    def initiate_workflow(
        self,
        *,
        config: AppConfig,
        request: InitiateWorkflowRequest | None = None,
    ) -> InitiateWorkflowResult:
        del config
        now = datetime.now(tz=UTC)
        workflow_id = (
            request.workflow_id
            if request and request.workflow_id
            else f"wf-{uuid.uuid4().hex[:12]}"
        )
        transition = TransitionRecord(
            transition_id=f"tr-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            from_state=WorkflowState.CREATED,
            to_state=WorkflowState.COLLECTING,
            reason="workflow_initiated",
            occurred_at=now,
            actor=request.actor if request else None,
        )
        record = _WorkflowRecord(
            workflow_id=workflow_id,
            state=WorkflowState.COLLECTING,
            state_version=1,
            created_at=now,
            updated_at=now,
            transitions=[transition],
            correlation_id=request.correlation_id if request else None,
            actor=request.actor if request else None,
        )
        self._workflows[workflow_id] = record
        enqueued = OutboxTaskSpec(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            task_type=TaskType.COLLECT,
            attempt=1,
            payload_reference=f"payload-{workflow_id}",
            idempotency_key=f"{workflow_id}:COLLECT:1",
            created_at=now,
        )
        return InitiateWorkflowResult(
            workflow_id=workflow_id,
            state=WorkflowState.COLLECTING,
            state_version=1,
            transition=transition,
            enqueued_task=enqueued,
        )

    def run_fake_provider_pipeline(self, workflow_id: str) -> None:
        """Advance COLLECTING → AWAITING_HUMAN_APPROVAL with fake provider artifacts.

        Holds a worker lease only while stages run; clears leases at approval wait
        (ACD-FR-013 / ACD-FR-065). Uses fake provider only (ACD-NFR-011).
        """
        record = self._require(workflow_id)
        if record.state == WorkflowState.AWAITING_HUMAN_APPROVAL:
            return
        if record.state != WorkflowState.COLLECTING:
            raise RuntimeError(
                f"pipeline expects COLLECTING, found {record.state.value}"
            )

        worker_id = "integration-fake-worker"
        task_id = f"task-pipeline-{workflow_id}"
        self._leases.append(_Lease(task_id=task_id, worker_id=worker_id))
        self.provider_id_used = "fake"

        now = datetime.now(tz=UTC)
        stages = (
            (WorkflowState.COLLECTING, WorkflowState.COLLECTED, "collect_completed"),
            (WorkflowState.COLLECTED, WorkflowState.SELECTING_TOPIC, "select_started"),
            (WorkflowState.SELECTING_TOPIC, WorkflowState.TOPIC_SELECTED, "topic_selected"),
            (WorkflowState.TOPIC_SELECTED, WorkflowState.GENERATING_SCENARIO, "generate_started"),
            (
                WorkflowState.GENERATING_SCENARIO,
                WorkflowState.SCENARIO_GENERATED,
                "scenario_generated",
            ),
            (WorkflowState.SCENARIO_GENERATED, WorkflowState.REVIEWING, "review_started"),
            (WorkflowState.REVIEWING, WorkflowState.REVIEW_PASSED, "critic_pass"),
            (
                WorkflowState.REVIEW_PASSED,
                WorkflowState.AWAITING_HUMAN_APPROVAL,
                "awaiting_human_approval",
            ),
        )
        for from_state, to_state, reason in stages:
            record.state = to_state
            record.state_version += 1
            record.updated_at = now
            record.transitions.append(
                TransitionRecord(
                    transition_id=f"tr-{uuid.uuid4().hex[:8]}",
                    workflow_id=workflow_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    occurred_at=now,
                    actor="fake-provider-pipeline",
                )
            )

        record.package = {
            "topic_selection": {
                "schema_version": 1,
                "outcome": "topic_selected",
                "selected_topic": "integration-topic",
                "provider": "fake",
            },
            "scenario": {
                "schema_version": 1,
                "title": "Integration Scenario",
                "provider": "fake",
            },
            "critic": {
                "schema_version": 1,
                "outcome": "pass",
                "provider": "fake",
            },
        }
        # Approval wait: no worker threads / leases held (ACD-FR-013).
        self._leases.clear()

    def apply_transition(self, request: TransitionRequest) -> TransitionResult:
        del request
        raise NotImplementedError(
            "ScenarioWorkflowEngine uses run_fake_provider_pipeline for stage progress"
        )

    def apply_approval_action(
        self,
        *,
        workflow_id: str,
        action: ApprovalAction,
        actor: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalActionResult:
        del idempotency_key
        record = self._require(workflow_id)
        if record.state != WorkflowState.AWAITING_HUMAN_APPROVAL:
            raise RuntimeError(
                f"approval requires AWAITING_HUMAN_APPROVAL, found {record.state.value}"
            )
        if action == ApprovalAction.APPROVE:
            to_state = WorkflowState.APPROVED
        elif action == ApprovalAction.REJECT:
            to_state = WorkflowState.REJECTED
        else:
            to_state = WorkflowState.GENERATING_SCENARIO
            record.revision_count += 1

        now = datetime.now(tz=UTC)
        from_state = record.state
        record.state = to_state
        record.state_version += 1
        record.updated_at = now
        transition = TransitionRecord(
            transition_id=f"tr-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            from_state=from_state,
            to_state=to_state,
            reason=f"approval_{action.value.lower()}",
            occurred_at=now,
            actor=actor,
        )
        record.transitions.append(transition)
        return ApprovalActionResult(
            workflow_id=workflow_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            state_version=record.state_version,
            transition_id=transition.transition_id,
            transition=transition,
            enqueued_task=None,
        )

    def reconcile_stuck_workflows(
        self,
        *,
        config: AppConfig,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        del config, batch_size
        return ReconciliationResult(scanned_count=0, repaired_count=0, reports=())

    def get_workflow_status(self, workflow_id: str) -> WorkflowStatus:
        record = self._require(workflow_id)
        return WorkflowStatus(
            workflow_id=record.workflow_id,
            state=record.state,
            state_version=record.state_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
            revision_count=record.revision_count,
            failure_reason=record.failure_reason,
        )

    def get_workflow_history(self, workflow_id: str) -> WorkflowHistory:
        record = self._require(workflow_id)
        return WorkflowHistory(
            workflow_id=workflow_id,
            transitions=tuple(record.transitions),
        )

    def get_workflow_output(self, workflow_id: str) -> WorkflowOutput:
        record = self._require(workflow_id)
        complete = record.state in {
            WorkflowState.APPROVED,
            WorkflowState.AWAITING_HUMAN_APPROVAL,
        }
        return WorkflowOutput(
            workflow_id=workflow_id,
            state=record.state,
            package=dict(record.package),
            is_complete=complete and bool(record.package),
            failure_reason=record.failure_reason,
        )

    def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimeline:
        self._require(workflow_id)
        return WorkflowTimeline(workflow_id=workflow_id, events=())

    def _require(self, workflow_id: str) -> _WorkflowRecord:
        record = self._workflows.get(workflow_id)
        if record is None:
            raise WorkflowNotFoundError(
                f"workflow not found: {workflow_id}",
                workflow_id=workflow_id,
            )
        return record
