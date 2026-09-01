"""Reconciliation scanner for stuck workflows (LLD §7)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Stuck-workflow recovery — detects state/outbox/queue
# mismatches (e.g. committed state without published task) and repairs automatically.

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from config.types import AppConfig, RetryPolicy, TaskType
from persistence.protocols import ArtifactRepo, OutboxRepo, TransactionManager, WorkflowRepo
from persistence.types import OutboxEntry, TaskRecord, TaskStatus, WorkflowRecord
from persistence.types import WorkflowState as PersistenceWorkflowState

from .constants import TERMINAL_STATES, TRANSIENT_STATES, stuck_threshold_seconds
from .executor import TransitionExecutor
from .outbox_builder import OutboxSpecBuilder
from .records import to_domain_workflow_state
from .transition_table import TransitionTable
from .types import (
    ReconciliationReport,
    ReconciliationResult,
    TransitionRequest,
    TransitionSignal,
    WorkflowState,
)

_IN_FLIGHT = frozenset(
    {TaskStatus.PENDING, TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS}
)

_PATTERN_PRIORITY = {"RP-003": 0, "RP-001": 1, "RP-002": 2, "RP-004": 3}


@dataclass(frozen=True, slots=True)
class ReconciliationCandidate:
    workflow: WorkflowRecord
    pattern_id: Literal["RP-001", "RP-002", "RP-003", "RP-004"]
    expected_task_type: TaskType | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class StuckStateEvaluation:
    is_stuck: bool
    threshold_seconds: float
    elapsed_seconds: float
    in_flight_task: bool


def _latest_task_of_type(
    tasks: Sequence[TaskRecord], task_type: TaskType
) -> TaskRecord | None:
    target = task_type.value
    matching = [
        t
        for t in tasks
        if getattr(t.task_type, "value", t.task_type) == target
        or t.task_type == task_type
    ]
    if not matching:
        return None
    return max(matching, key=lambda t: t.created_at)


def _has_unpublished(unpublished: Sequence[OutboxEntry], task_type: TaskType) -> bool:
    return any(e.task_type == task_type for e in unpublished)


class ReconciliationScanner:
    """Detects and repairs incomplete workflow transitions."""

    def __init__(
        self,
        *,
        config: AppConfig,
        workflow_repo: WorkflowRepo,
        outbox_repo: OutboxRepo,
        artifact_repo: ArtifactRepo,
        executor: TransitionExecutor,
        outbox_builder: OutboxSpecBuilder,
        transition_table: TransitionTable,
        engine: object,
        transaction_guard: object,
        transaction_manager: TransactionManager,
        clock: Callable[[], datetime] | None = None,
        stuck_threshold_overrides: Mapping[WorkflowState, float] | None = None,
    ) -> None:
        self._config = config
        self._workflow_repo = workflow_repo
        self._outbox_repo = outbox_repo
        self._artifact_repo = artifact_repo
        self._executor = executor
        self._outbox_builder = outbox_builder
        self._transition_table = transition_table
        self._engine = engine
        self._transaction_guard = transaction_guard
        self._transaction_manager = transaction_manager
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stuck_overrides = stuck_threshold_overrides or {}

    def _threshold_for(self, state: WorkflowState) -> float:
        if state in self._stuck_overrides:
            return self._stuck_overrides[state]
        return stuck_threshold_seconds(state)

    def _rp001_expected_task(
        self,
        *,
        workflow: WorkflowRecord,
        tasks: Sequence[TaskRecord],
        unpublished: Sequence[OutboxEntry],
    ) -> TaskType | None:
        state = to_domain_workflow_state(workflow.state.value)
        base = self._transition_table.expected_outbox_task(state)
        if state != WorkflowState.GENERATING_SCENARIO:
            return base
        latest_gen = _latest_task_of_type(tasks, TaskType.GENERATE_SCENARIO)
        if latest_gen is None:
            return None
        if latest_gen.status in _IN_FLIGHT:
            return None
        if _has_unpublished(unpublished, TaskType.GENERATE_SCENARIO):
            return None
        return TaskType.GENERATE_SCENARIO

    def is_stuck_retriable(
        self,
        *,
        latest_task: TaskRecord | None,
        retry_policy: RetryPolicy,
    ) -> bool:
        current_attempt = latest_task.attempt if latest_task is not None else 0
        return current_attempt < retry_policy.max_attempts

    def _evaluate_rp003(
        self,
        *,
        workflow: WorkflowRecord,
        latest_task: TaskRecord | None,
    ) -> StuckStateEvaluation:
        state = to_domain_workflow_state(workflow.state.value)
        threshold = self._threshold_for(state)
        now = self._clock()
        elapsed = (now - workflow.updated_at).total_seconds()
        in_flight = latest_task is not None and latest_task.status in _IN_FLIGHT
        is_stuck = elapsed > threshold and not in_flight
        return StuckStateEvaluation(
            is_stuck=is_stuck,
            threshold_seconds=threshold,
            elapsed_seconds=elapsed,
            in_flight_task=in_flight,
        )

    def _dedupe_candidates(
        self, candidates: Sequence[ReconciliationCandidate]
    ) -> list[ReconciliationCandidate]:
        by_id: dict[str, ReconciliationCandidate] = {}
        for candidate in candidates:
            existing = by_id.get(candidate.workflow.workflow_id)
            if existing is None:
                by_id[candidate.workflow.workflow_id] = candidate
                continue
            if _PATTERN_PRIORITY[candidate.pattern_id] < _PATTERN_PRIORITY[
                existing.pattern_id
            ]:
                by_id[candidate.workflow.workflow_id] = candidate
        return list(by_id.values())

    def _list_unpublished(self, workflow_id: str) -> Sequence[OutboxEntry]:
        list_fn = getattr(self._outbox_repo, "list_unpublished_outbox_for_workflow", None)
        if callable(list_fn):
            return list_fn(workflow_id)
        return []

    def _list_tasks(self, workflow_id: str) -> Sequence[TaskRecord]:
        list_fn = getattr(self._workflow_repo, "list_tasks_for_workflow", None)
        if callable(list_fn):
            return list_fn(workflow_id)
        return []

    def collect_candidates(self, batch_size: int) -> list[ReconciliationCandidate]:
        now = self._clock()
        candidates: list[ReconciliationCandidate] = []

        for state in TRANSIENT_STATES:
            threshold = self._threshold_for(state)
            updated_before = now - timedelta(seconds=threshold)
            list_fn = getattr(self._workflow_repo, "list_workflows_for_reconciliation", None)
            if not callable(list_fn):
                continue
            rows = list_fn(
                states=[PersistenceWorkflowState(state.value)],
                updated_before=updated_before,
                limit=batch_size,
            )
            for row in rows:
                tasks = self._list_tasks(row.workflow_id)
                expected = self._rp001_expected_task(
                    workflow=row,
                    tasks=tasks,
                    unpublished=self._list_unpublished(row.workflow_id),
                )
                latest = (
                    _latest_task_of_type(tasks, expected)
                    if expected is not None
                    else None
                )
                evaluation = self._evaluate_rp003(workflow=row, latest_task=latest)
                if evaluation.is_stuck:
                    candidates.append(
                        ReconciliationCandidate(
                            workflow=row,
                            pattern_id="RP-003",
                            expected_task_type=expected,
                        )
                    )

        scan_states = {
            WorkflowState.COLLECTING,
            WorkflowState.COLLECTED,
            WorkflowState.TOPIC_SELECTED,
            WorkflowState.SCENARIO_GENERATED,
            WorkflowState.GENERATING_SCENARIO,
        }
        list_fn = getattr(self._workflow_repo, "list_workflows_for_reconciliation", None)
        if callable(list_fn):
            pers_states = [PersistenceWorkflowState(s.value) for s in scan_states]
            rows = list_fn(states=pers_states, limit=batch_size)
            for row in rows:
                domain_state = to_domain_workflow_state(row.state.value)
                if domain_state in TERMINAL_STATES:
                    continue
                unpublished = self._list_unpublished(row.workflow_id)
                if unpublished:
                    candidates.append(
                        ReconciliationCandidate(
                            workflow=row,
                            pattern_id="RP-002",
                            detail="outbox_pending_publish",
                        )
                    )
                    continue
                tasks = self._list_tasks(row.workflow_id)
                expected = self._rp001_expected_task(
                    workflow=row, tasks=tasks, unpublished=unpublished
                )
                if expected is not None:
                    candidates.append(
                        ReconciliationCandidate(
                            workflow=row,
                            pattern_id="RP-001",
                            expected_task_type=expected,
                        )
                    )

        fetch_fn = getattr(self._outbox_repo, "fetch_unpublished", None)
        if callable(fetch_fn):
            seen_ids = {c.workflow.workflow_id for c in candidates}
            for entry in fetch_fn(batch_size):
                if entry.workflow_id in seen_ids:
                    continue
                row = self._workflow_repo.get_workflow(entry.workflow_id)
                if row is None:
                    continue
                domain_state = to_domain_workflow_state(row.state.value)
                if domain_state in TERMINAL_STATES:
                    candidates.append(
                        ReconciliationCandidate(
                            workflow=row,
                            pattern_id="RP-004",
                            detail="terminal_unpublished_outbox",
                        )
                    )
                    seen_ids.add(entry.workflow_id)

        deduped = self._dedupe_candidates(candidates)
        return deduped[:batch_size]

    def _run_guarded(self, operation: str, fn: Callable[[], object]) -> object:
        require = getattr(self._transaction_guard, "require_active", None)
        if callable(require):
            require(operation=operation)
        return fn()

    def _in_transaction(self, fn: Callable[[], object]) -> object:
        if getattr(self._transaction_manager, "is_in_transaction", lambda: False)():
            return fn()
        with self._transaction_manager.transaction():
            return fn()

    def _get_retry_policy(self, task_type: TaskType) -> RetryPolicy:
        getter = getattr(self._config, "get_retry_policy", None)
        if callable(getter):
            try:
                return getter(task_type)
            except NotImplementedError:
                pass
        policy = self._config.retry.get(task_type)
        if policy is not None:
            return policy
        from config.types import BackoffConfig

        return RetryPolicy(
            max_attempts=3,
            backoff=BackoffConfig(
                initial_seconds=1.0, multiplier=2.0, max_seconds=30.0
            ),
        )

    def scan_and_repair(self, *, batch_size: int = 100) -> ReconciliationResult:
        candidates = self.collect_candidates(batch_size)
        reports: list[ReconciliationReport] = []
        repaired_count = 0

        for candidate in candidates:
            fresh = self._workflow_repo.get_workflow(candidate.workflow.workflow_id)
            if (
                fresh is None
                or fresh.state_version != candidate.workflow.state_version
            ):
                reports.append(
                    ReconciliationReport(
                        workflow_id=candidate.workflow.workflow_id,
                        repair_action=candidate.pattern_id,
                        repaired=False,
                        detail="version_mismatch_skip",
                    )
                )
                continue

            if candidate.pattern_id == "RP-002":
                reports.append(
                    ReconciliationReport(
                        workflow_id=candidate.workflow.workflow_id,
                        repair_action="RP-002",
                        repaired=False,
                        detail="outbox_pending_publish",
                    )
                )
                continue

            if candidate.pattern_id == "RP-004":
                reports.append(
                    ReconciliationReport(
                        workflow_id=candidate.workflow.workflow_id,
                        repair_action="RP-004",
                        repaired=False,
                        detail="terminal_unpublished_outbox",
                    )
                )
                continue

            if candidate.pattern_id == "RP-001":
                def repair_rp001() -> None:
                    self._run_guarded(
                        "reconcile_stuck_workflows",
                        lambda: self._executor.recreate_expected_outbox(
                            workflow=fresh,
                            expected_task_type=candidate.expected_task_type,
                            artifact_repo=self._artifact_repo,
                            outbox_builder=self._outbox_builder,
                        ),
                    )

                self._in_transaction(repair_rp001)
                repaired_count += 1
                reports.append(
                    ReconciliationReport(
                        workflow_id=candidate.workflow.workflow_id,
                        repair_action="RP-001",
                        repaired=True,
                    )
                )
                continue

            if candidate.pattern_id == "RP-003":
                tasks = self._list_tasks(fresh.workflow_id)
                expected = candidate.expected_task_type
                latest = (
                    _latest_task_of_type(tasks, expected) if expected is not None else None
                )
                evaluation = self._evaluate_rp003(workflow=fresh, latest_task=latest)
                if not evaluation.is_stuck:
                    reports.append(
                        ReconciliationReport(
                            workflow_id=candidate.workflow.workflow_id,
                            repair_action="RP-003",
                            repaired=False,
                        )
                    )
                    continue

                retry_policy = self._get_retry_policy(expected or TaskType.COLLECT)
                if self.is_stuck_retriable(
                    latest_task=latest, retry_policy=retry_policy
                ) and expected is not None:
                    retry_attempt = (latest.attempt if latest is not None else 0) + 1

                    def repair_retry() -> None:
                        self._run_guarded(
                            "reconcile_stuck_workflows",
                            lambda: self._executor.recreate_expected_outbox(
                                workflow=fresh,
                                expected_task_type=expected,
                                artifact_repo=self._artifact_repo,
                                outbox_builder=self._outbox_builder,
                                attempt=retry_attempt,
                            ),
                        )

                    self._in_transaction(repair_retry)
                    repaired_count += 1
                    reports.append(
                        ReconciliationReport(
                            workflow_id=candidate.workflow.workflow_id,
                            repair_action="RP-003",
                            repaired=True,
                            detail="outbox_retry",
                        )
                    )
                else:

                    def repair_failed() -> None:
                        self._run_guarded(
                            "reconcile_stuck_workflows",
                            lambda: self._engine.apply_transition(  # type: ignore[attr-defined]
                                TransitionRequest(
                                    workflow_id=fresh.workflow_id,
                                    expected_state=to_domain_workflow_state(
                                        fresh.state.value
                                    ),
                                    signal=TransitionSignal.RECONCILIATION_REPAIR,
                                    reason="stuck_state_timeout",
                                )
                            ),
                        )

                    self._in_transaction(repair_failed)
                    repaired_count += 1
                    reports.append(
                        ReconciliationReport(
                            workflow_id=candidate.workflow.workflow_id,
                            repair_action="RP-003",
                            repaired=True,
                        )
                    )

        return ReconciliationResult(
            scanned_count=len(candidates),
            repaired_count=repaired_count,
            reports=tuple(reports),
        )
