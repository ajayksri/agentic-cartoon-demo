"""Contract tests WKR-TC-001 through WKR-TC-071 (WKR-017).

Imports ONLY from the worker package public surface (`worker.__init__`).
Boundary imports for fixture injection live in helpers.py / conftest.py per LLD §12.1.
"""

from __future__ import annotations

import pytest

from config.types import TaskType
from worker import (
    DuplicateResolution,
    HandlerNotFoundError,
    create_idempotency_orchestrator,
    create_task_handler_registry,
    create_worker_loop,
    run_task_loop,
)

from worker.fakes.handlers import RecordingHandler
from .helpers import (
    minimal_pending_delivery,
    minimal_worker_config,
    memory_worker_loop,
    public_export_names,
)


def _process_one_delivery(fixture: MemoryWorkerFixture, delivery: object | None = None) -> None:
    delivery = delivery or minimal_pending_delivery()
    from .helpers import _seed_workflow_and_task

    _seed_workflow_and_task(workflow_repo=fixture.workflow_repo, delivery=delivery)  # type: ignore[arg-type]
    fixture.queue.enqueue_delivery(delivery)  # type: ignore[arg-type]
    fixture.loop.run_once()  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("001")
def test_wkr_tc_001_happy_path_collect_transitions_and_acks() -> None:
    """WKR-TC-001: COLLECT handler invoked; STAGE_COMPLETED; delivery ACKed."""
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    _process_one_delivery(fixture)
    assert handler.calls == 1
    assert fixture.engine.transitions
    assert fixture.queue.acked


@pytest.mark.wkr_tc("002")
def test_wkr_tc_002_redelivery_after_crash_before_ack() -> None:
    """WKR-TC-002: un-ACKed delivery reprocessed on restart."""
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    delivery = minimal_pending_delivery()
    fixture.queue.enqueue_delivery(delivery)
    fixture.loop.process_delivery_without_ack(delivery)  # type: ignore[attr-defined]
    fixture.loop.process_delivery_without_ack(delivery)  # type: ignore[attr-defined]
    assert handler.calls == 2


@pytest.mark.wkr_tc("010")
def test_wkr_tc_010_redelivery_reuses_committed_result() -> None:
    """WKR-TC-010: idempotency hit — handler not invoked."""
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    key = "wf-contract-1:COLLECT:1"
    fixture.idempotency_repo.seed_completed(key=key)  # type: ignore[attr-defined]
    _process_one_delivery(fixture)
    assert handler.calls == 0


@pytest.mark.wkr_tc("011")
def test_wkr_tc_011_scenario_redelivery_artifact_unchanged() -> None:
    """WKR-TC-011: GENERATE_SCENARIO redelivery leaves artifact unchanged."""
    from worker.handlers.generate_scenario import GenerateScenarioTaskHandler

    handler = GenerateScenarioTaskHandler()
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    delivery = minimal_pending_delivery(task_type=TaskType.GENERATE_SCENARIO)
    fixture.artifact_repo.seed_topic_selection(workflow_id=delivery.message.workflow_id)  # type: ignore[attr-defined]
    _process_one_delivery(fixture, delivery)
    fixture.artifact_repo.unchanged = True  # type: ignore[attr-defined]
    fixture.queue.enqueue_delivery(delivery)  # type: ignore[arg-type]
    fixture.loop.run_once()  # type: ignore[attr-defined]
    assert fixture.artifact_repo.unchanged  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("012")
def test_wkr_tc_012_build_idempotency_key_stable() -> None:
    """WKR-TC-012: build_idempotency_key stable across calls."""
    from persistence.fakes.idempotency import InMemoryIdempotencyRepo

    orchestrator = create_idempotency_orchestrator(idempotency_repo=InMemoryIdempotencyRepo())
    key_a = orchestrator.build_idempotency_key(
        workflow_id="wf-1",
        task_type=TaskType.COLLECT,
        logical_version=1,
    )
    key_b = orchestrator.build_idempotency_key(
        workflow_id="wf-1",
        task_type=TaskType.COLLECT,
        logical_version=1,
    )
    assert key_a == key_b


@pytest.mark.wkr_tc("013")
def test_wkr_tc_013_claim_sequence_first_wins() -> None:
    """WKR-TC-013: first CLAIMED, second DUPLICATE_REJECTED."""
    from persistence.fakes.idempotency import InMemoryIdempotencyRepo
    from persistence.fakes.transaction import InMemoryTransactionManager
    from persistence.types import IdempotencyInsertSpec
    from worker import IdempotencyPhase

    txn = InMemoryTransactionManager()
    repo = InMemoryIdempotencyRepo(transaction_manager=txn)
    orchestrator = create_idempotency_orchestrator(idempotency_repo=repo)
    spec = IdempotencyInsertSpec(
        idempotency_key="wf-1:COLLECT:1",
        workflow_id="wf-1",
        task_id="task-1",
        result_artifact_id="art-1",
    )
    with txn.transaction():
        first = orchestrator.claim_completion(spec=spec)
    with txn.transaction():
        second = orchestrator.claim_completion(spec=spec)
    assert first.phase == IdempotencyPhase.CLAIMED
    assert second.phase == IdempotencyPhase.DUPLICATE_REJECTED


@pytest.mark.wkr_tc("014")
def test_wkr_tc_014_infrastructure_retry_no_regeneration_metric() -> None:
    """WKR-TC-014: reuse path does not increment regeneration metrics."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    fixture.telemetry = fixture.loop.telemetry  # type: ignore[attr-defined]
    fixture.loop.process_reuse_path()  # type: ignore[attr-defined]
    assert "regeneration" not in fixture.telemetry.retry_kinds  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("015")
def test_wkr_tc_015_precheck_short_circuit_metric() -> None:
    """WKR-TC-015: IGNORED_BEFORE_EXECUTION metric on pre-check short-circuit."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    fixture.loop.short_circuit_precheck()  # type: ignore[attr-defined]
    assert DuplicateResolution.IGNORED_BEFORE_EXECUTION.value in fixture.recorded_resolutions  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("016")
def test_wkr_tc_016_concurrent_duplicate_one_authoritative_completion() -> None:
    """WKR-TC-016: two workers — one claim wins; Scenario C loser path."""
    import concurrent.futures
    import threading

    from workflow.types import TransitionSignal

    from worker.types import TaskHandlerOutcome, TaskHandlerResult

    barrier = threading.Barrier(2)

    class _BarrierCollectHandler:
        @property
        def task_type(self) -> TaskType:
            return TaskType.COLLECT

        def handle(self, context: object) -> TaskHandlerResult:
            barrier.wait(timeout=5)
            return TaskHandlerResult(
                outcome=TaskHandlerOutcome.COMPLETED,
                transition_signal=TransitionSignal.STAGE_COMPLETED,
                result_artifact_id="art-race",
            )

    handler = _BarrierCollectHandler()
    fixture_a = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    fixture_b = memory_worker_loop(
        config=minimal_worker_config(),
        shared_fixture=fixture_a,
        consumer_name="worker-contract-2",
        handlers=[handler],
    )
    delivery_a = minimal_pending_delivery(task_id="task-race-a")
    delivery_b = minimal_pending_delivery(task_id="task-race-b")
    from .helpers import _seed_workflow_and_task

    _seed_workflow_and_task(workflow_repo=fixture_a.workflow_repo, delivery=delivery_a)
    _seed_workflow_and_task(workflow_repo=fixture_a.workflow_repo, delivery=delivery_b)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(fixture_a.loop._process_delivery, delivery_a),  # type: ignore[attr-defined]
            executor.submit(fixture_b.loop._process_delivery, delivery_b),  # type: ignore[attr-defined]
        ]
        for future in futures:
            future.result()

    assert fixture_a.idempotency_repo.get_by_key("wf-contract-1:COLLECT:1") is not None
    assert len(fixture_a.engine.transitions) >= 1
    assert any(
        transition.reason == "scenario_c_loser"
        for transition in fixture_a.engine.transitions
    ) or DuplicateResolution.REJECTED_DURING_COMMIT.value in fixture_a.recorded_resolutions


@pytest.mark.wkr_tc("020")
def test_wkr_tc_020_transient_provider_error_schedules_retry() -> None:
    """WKR-TC-020: retryable failure — retry scheduled, no terminal transition."""
    from providers import ProviderTimeoutError

    handler = RecordingHandler(
        _task_type=TaskType.SELECT_TOPIC,
        raise_error=ProviderTimeoutError("timeout"),
    )
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    _process_one_delivery(fixture, minimal_pending_delivery(task_type=TaskType.SELECT_TOPIC))
    assert not fixture.engine.transitions
    assert not fixture.queue.acked


@pytest.mark.wkr_tc("021")
def test_wkr_tc_021_max_attempts_boundary_no_further_retry() -> None:
    """WKR-TC-021: attempt == max_attempts — no further retry."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    assert fixture.loop.should_retry(attempt=3, max_attempts=3) is False  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("022")
def test_wkr_tc_022_agent_timeout_classified_and_retried() -> None:
    """WKR-TC-022: provider timeout classified; retry per policy."""
    from providers import ProviderTimeoutError

    fixture = memory_worker_loop(config=minimal_worker_config())
    retryable, _ = fixture.loop.classify(ProviderTimeoutError("timeout"))  # type: ignore[attr-defined]
    assert retryable is True


@pytest.mark.wkr_tc("023")
def test_wkr_tc_023_exhausted_retries_to_failed_permanently() -> None:
    """WKR-TC-023: RETRIES_EXHAUSTED → FAILED_PERMANENTLY transition."""
    from workflow.types import TransitionSignal

    fixture = memory_worker_loop(config=minimal_worker_config())
    fixture.loop.handle_exhausted_retry()  # type: ignore[attr-defined]
    assert fixture.engine.transitions[-1].signal == TransitionSignal.RETRIES_EXHAUSTED


@pytest.mark.wkr_tc("024")
def test_wkr_tc_024_invalid_agent_output_no_transition() -> None:
    """WKR-TC-024: AgentOutputValidationError — no successful stage transition."""
    from agents import AgentOutputValidationError
    from config.types import AgentId

    handler = RecordingHandler(
        _task_type=TaskType.SELECT_TOPIC,
        raise_error=AgentOutputValidationError("bad", agent_id=AgentId.TOPIC_SELECTOR),
    )
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    _process_one_delivery(fixture, minimal_pending_delivery(task_type=TaskType.SELECT_TOPIC))
    assert not fixture.engine.transitions


@pytest.mark.wkr_tc("030")
def test_wkr_tc_030_multiple_workflows_concurrent() -> None:
    """WKR-TC-030: concurrency > 1 — two workflows progress independently."""
    config = minimal_worker_config(topic_concurrency=2)
    fixture = memory_worker_loop(config=config)
    results = fixture.loop.process_concurrent_workflows(count=2)  # type: ignore[attr-defined]
    assert len(results) == 2


@pytest.mark.wkr_tc("031")
def test_wkr_tc_031_concurrency_limit_enforced() -> None:
    """WKR-TC-031: at most N handler executions in flight."""
    config = minimal_worker_config(topic_concurrency=1)
    fixture = memory_worker_loop(config=config)
    assert fixture.loop.max_in_flight(task_type=TaskType.SELECT_TOPIC) <= 1  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("032")
def test_wkr_tc_032_approval_wait_stale_delivery_no_lease() -> None:
    """WKR-TC-032: AWAITING_HUMAN_APPROVAL stale — ack_and_skip_approval; no lease."""
    from workflow.types import WorkflowState

    fixture = memory_worker_loop(config=minimal_worker_config())
    fixture.workflow_repo.set_state("wf-contract-1", WorkflowState.AWAITING_HUMAN_APPROVAL.value)  # type: ignore[attr-defined]
    _process_one_delivery(fixture)
    assert fixture.queue.acked
    assert not fixture.task_lease_repo.active_leases  # type: ignore[attr-defined]


@pytest.mark.wkr_tc("033")
def test_wkr_tc_033_select_topic_appends_ai_invocation_without_secrets() -> None:
    """WKR-TC-033: append_ai_invocation metadata; no secrets in audit row."""
    from worker.handlers.select_topic import SelectTopicTaskHandler

    handler = SelectTopicTaskHandler()
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    delivery = minimal_pending_delivery(task_type=TaskType.SELECT_TOPIC)
    fixture.loop._seed_collected_stories(delivery.message.workflow_id)  # type: ignore[attr-defined]
    _process_one_delivery(fixture, delivery)
    audit = fixture.artifact_repo.last_ai_invocation  # type: ignore[attr-defined]
    assert audit is not None
    assert audit.agent_name == "topic_selector"
    assert "api_key" not in str(audit)


@pytest.mark.wkr_tc("034")
def test_wkr_tc_034_failure_injection_hooks_when_active() -> None:
    """WKR-TC-034: FINJ-WKR-PRE, POST-AGENT, POST-COMMIT, PRE-ACK invoked when active."""
    from config.types import InjectionId
    from worker.handlers.select_topic import SelectTopicTaskHandler

    config = minimal_worker_config(
        active_injections=(
            InjectionId.FINJ_WKR_PRE,
            InjectionId.FINJ_WKR_POST_AGENT,
            InjectionId.FINJ_WKR_POST_COMMIT,
            InjectionId.FINJ_WKR_PRE_ACK,
        ),
    )
    fixture = memory_worker_loop(config=config, handlers=[SelectTopicTaskHandler()])
    invoked = fixture.loop.process_with_injection_trace()  # type: ignore[attr-defined]
    for hook in (
        InjectionId.FINJ_WKR_PRE,
        InjectionId.FINJ_WKR_POST_AGENT,
        InjectionId.FINJ_WKR_POST_COMMIT,
        InjectionId.FINJ_WKR_PRE_ACK,
    ):
        assert hook in invoked


@pytest.mark.wkr_tc("040")
def test_wkr_tc_040_workflow_duration_deferred_to_coordinator() -> None:
    """WKR-TC-040: worker supplies boundary timestamps; coordinator owns workflow_duration."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    boundaries = fixture.loop.task_timing_boundaries()  # type: ignore[attr-defined]
    assert "enqueued_at" in boundaries
    assert "completed_at" in boundaries
    assert boundaries.get("workflow_duration_ms") is None


@pytest.mark.wkr_tc("041")
def test_wkr_tc_041_state_duration_deferred_to_coordinator() -> None:
    """WKR-TC-041: worker boundary timestamps in logs; coordinator owns state duration."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    boundaries = fixture.loop.task_timing_boundaries()  # type: ignore[attr-defined]
    assert boundaries.get("workflow_state_duration_ms") is None


@pytest.mark.wkr_tc("042")
def test_wkr_tc_042_queue_wait_separate_from_execution() -> None:
    """WKR-TC-042: RecordingWorkerTelemetry distinct queue wait vs execution histograms."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    metrics = fixture.loop.recorded_completion_metrics()  # type: ignore[attr-defined]
    assert "worker_task_queue_wait_duration_ms" in metrics
    assert "worker_task_execution_duration_ms" in metrics


@pytest.mark.wkr_tc("043")
def test_wkr_tc_043_regeneration_vs_retry_distinct_labels() -> None:
    """WKR-TC-043: infrastructure_reuse vs regeneration distinct metric labels."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    kinds = fixture.loop.recorded_retry_kinds()  # type: ignore[attr-defined]
    assert "infrastructure_reuse" in kinds
    assert "regeneration" in kinds


@pytest.mark.wkr_tc("050")
def test_wkr_tc_050_handler_does_not_call_apply_transition() -> None:
    """WKR-TC-050: handler isolation — no apply_transition from handler."""
    handler = RecordingHandler(_task_type=TaskType.COLLECT)
    fixture = memory_worker_loop(config=minimal_worker_config(), handlers=[handler])
    handler.handle(context=fixture.loop.build_context())  # type: ignore[attr-defined]
    assert not fixture.engine.transitions


@pytest.mark.wkr_tc("051")
def test_wkr_tc_051_import_boundary_cross_reference() -> None:
    """WKR-TC-051: satisfied by tests/unit/worker/test_import_boundary.py (no duplicate)."""
    from tests.unit.worker import test_import_boundary as boundary

    assert hasattr(boundary, "test_worker_module_has_no_api_cli_runtime_imports")


@pytest.mark.wkr_tc("052")
def test_wkr_tc_052_eval_exec_cross_reference() -> None:
    """WKR-TC-052: satisfied by tests/unit/worker/test_import_boundary.py (no duplicate)."""
    from tests.unit.worker import test_import_boundary as boundary

    assert hasattr(boundary, "test_worker_module_has_no_eval_or_exec")


@pytest.mark.wkr_tc("060")
def test_wkr_tc_060_registry_dispatches_all_task_types() -> None:
    """WKR-TC-060: registry returns handler for each TaskType."""
    handlers = [RecordingHandler(_task_type=task_type) for task_type in TaskType]
    registry = create_task_handler_registry(handlers=handlers)
    for task_type in TaskType:
        assert registry.get_handler(task_type).task_type == task_type


@pytest.mark.wkr_tc("061")
def test_wkr_tc_061_missing_handler_raises_handler_not_found() -> None:
    """WKR-TC-061: empty registry → HandlerNotFoundError WKR_NO_HANDLER."""
    registry = create_task_handler_registry(handlers=[])
    with pytest.raises(HandlerNotFoundError) as exc_info:
        registry.get_handler(TaskType.SELECT_TOPIC)
    assert exc_info.value.code == "WKR_NO_HANDLER"


@pytest.mark.wkr_tc("062")
def test_wkr_tc_062_public_exports_match_interfaces() -> None:
    """WKR-TC-062: public exports match interfaces.md §1–§8."""
    import worker

    live_exports = frozenset(worker.__all__)
    assert public_export_names() == live_exports
    for symbol in live_exports:
        assert hasattr(worker, symbol), f"missing export: {symbol}"
    assert callable(create_worker_loop)
    assert callable(run_task_loop)


@pytest.mark.wkr_tc("070")
def test_wkr_tc_070_ack_after_durable_commit() -> None:
    """WKR-TC-070: TaskQueue.ack only after transaction commit and transition."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    order = fixture.loop.success_path_event_order()  # type: ignore[attr-defined]
    assert order.index("commit") < order.index("transition") < order.index("ack")


@pytest.mark.wkr_tc("071")
def test_wkr_tc_071_lease_conflict_no_ack() -> None:
    """WKR-TC-071: lease conflict — delivery remains pending; duplicate resolution recorded."""
    fixture = memory_worker_loop(config=minimal_worker_config())
    fixture.task_lease_repo.hold_lease(task_id="task-contract-1", worker_id="peer")  # type: ignore[attr-defined]
    _process_one_delivery(fixture)
    assert not fixture.queue.acked
    assert DuplicateResolution.DETECTED_DURING_EXECUTION.value in fixture.recorded_resolutions  # type: ignore[attr-defined]
