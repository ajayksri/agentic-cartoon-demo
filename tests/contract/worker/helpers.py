"""Shared contract-test helpers for worker module (WKR-017, LLD §12.1)."""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from config.app_config import AppConfigFactory
from config.credentials import CredentialResolver
from config.draft import (
    AgentDraft,
    BackoffDraft,
    CollectionDraft,
    ConfigDraft,
    FailureInjectionDraft,
    InfrastructureDraft,
    PostgresDraft,
    ProviderDraft,
    RedisDraft,
    RetryPolicyDraft,
    TimeoutDraft,
    WorkerDraft,
    WorkflowDraft,
)
from config.types import AgentId, AppConfig, InjectionId, ProviderId, TaskType
from persistence.fakes.artifact import InMemoryArtifactRepo
from persistence.fakes.idempotency import InMemoryIdempotencyRepo
from persistence.fakes.task_lease import InMemoryTaskLeaseRepo
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.fakes.workflow import InMemoryWorkflowRepo
from persistence.types import (
    IdempotencyRecord,
    PayloadReference,
    TaskRecord,
    TaskStatus,
    TaskType as PersTaskType,
    WorkflowState as PersWorkflowState,
)
from task_queue import PendingDelivery, TaskMessage
from worker import (
    TaskHandler,
    TaskHandlerOutcome,
    TaskHandlerResult,
    WorkerLoop,
    WorkerLoopConfig,
    create_idempotency_orchestrator,
    create_task_handler_registry,
    create_worker_loop,
)
from worker.fakes.handlers import RecordingHandler
from worker.fakes.task_queue import FakeTaskQueue
from worker.fakes.workflow_engine import FakeWorkflowEngine
from worker.telemetry import RecordingWorkerTelemetry
from workflow.types import TransitionRequest, TransitionSignal, WorkflowState

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


class ContractWorkflowRepo(InMemoryWorkflowRepo):
    """Workflow repo with contract-test helpers."""

    def set_state(self, workflow_id: str, state: str) -> None:
        existing = self.get_workflow(workflow_id)
        if existing is None:
            self.create_workflow(workflow_id, initial_state=PersWorkflowState(state))
            return
        self._workflows[workflow_id] = type(existing)(
            workflow_id=existing.workflow_id,
            state=PersWorkflowState(state),
            state_version=existing.state_version,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            revision_count=existing.revision_count,
            failure_reason=existing.failure_reason,
        )

    def upsert_task(self, task: TaskRecord) -> TaskRecord:
        with self._transaction_manager.transaction():  # type: ignore[union-attr]
            self._tasks[task.task_id] = task
            self._payloads[task.payload_reference.ref_id] = {}
        return task


class ContractArtifactRepo(InMemoryArtifactRepo):
    """Artifact repo with contract-test helpers."""

    unchanged: bool = True
    last_ai_invocation: object | None = None

    def create_artifact(self, spec: object) -> object:
        self.unchanged = False
        return super().create_artifact(spec)  # type: ignore[arg-type]

    def append_ai_invocation(self, spec: object) -> object:
        record = super().append_ai_invocation(spec)  # type: ignore[arg-type]
        self.last_ai_invocation = record
        return record

    def seed_scenario(self, *, workflow_id: str, content: dict[str, object]) -> None:
        from persistence.types import ArtifactCreateSpec, ArtifactType

        with self._transaction_manager.transaction():  # type: ignore[union-attr]
            self.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.SCENARIO,
                    name="scenario",
                    version=content.get("logical_version", 1),
                    logical_version=int(content.get("logical_version", 1)),
                    content=content,
                )
            )
        self.unchanged = True

    def seed_topic_selection(
        self,
        *,
        workflow_id: str,
        content: dict[str, object] | None = None,
    ) -> None:
        from persistence.types import ArtifactCreateSpec, ArtifactType

        topic_content = content or {
            "schema_version": 1,
            "outcome": "topic_selected",
            "selected_topic": "topic",
            "why_interesting": "interesting",
            "cartoon_angle": "angle",
        }
        with self._transaction_manager.transaction():  # type: ignore[union-attr]
            self.create_artifact(
                ArtifactCreateSpec(
                    workflow_id=workflow_id,
                    artifact_type=ArtifactType.TOPIC_SELECTION,
                    name="topic_selection",
                    version=1,
                    logical_version=1,
                    content=topic_content,
                )
            )
        self.unchanged = True


class ContractIdempotencyRepo(InMemoryIdempotencyRepo):
    """Idempotency repo with contract-test helpers."""

    def seed_completed(self, *, key: str) -> None:
        from persistence.types import IdempotencyInsertSpec

        with self._transaction_manager.transaction():  # type: ignore[union-attr]
            self.try_insert(
                IdempotencyInsertSpec(
                    idempotency_key=key,
                    workflow_id="wf-contract-1",
                    task_id="task-contract-1",
                    result_artifact_id="art-seeded",
                )
            )


class ContractTaskLeaseRepo(InMemoryTaskLeaseRepo):
    """Lease repo with contract-test helpers."""

    @property
    def active_leases(self) -> list[object]:
        return list(self._leases.values())

    def hold_lease(self, *, task_id: str, worker_id: str) -> None:
        self.try_acquire(task_id, worker_id=worker_id, ttl_seconds=60.0)


@dataclass
class MemoryWorkerFixture:
    loop: WorkerLoop
    queue: FakeTaskQueue
    engine: FakeWorkflowEngine
    txn: InMemoryTransactionManager
    idempotency_repo: ContractIdempotencyRepo
    workflow_repo: ContractWorkflowRepo
    artifact_repo: ContractArtifactRepo
    task_lease_repo: ContractTaskLeaseRepo
    recorded_resolutions: list[str] = field(default_factory=list)


def minimal_worker_config(
    *,
    topic_concurrency: int = 2,
    active_injections: Sequence[InjectionId] = (),
) -> AppConfig:
    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    draft = ConfigDraft(
        config_version="1",
        infrastructure=InfrastructureDraft(
            postgres=PostgresDraft(
                host="localhost",
                port=5432,
                database="cartoon",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisDraft(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/topic_selector.txt",
            ),
            AgentId.SCENARIO_GENERATOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/scenario_generator.txt",
            ),
            AgentId.CRITIC: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/critic.txt",
            ),
        },
        providers={
            ProviderId.FAKE: ProviderDraft(
                api_key_env="FAKE_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=10, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=topic_concurrency,
            scenario_generator_concurrency=topic_concurrency,
            critic_concurrency=topic_concurrency,
        ),
        retry={task: copy.deepcopy(retry_policy) for task in TaskType},
        timeouts={
            ProviderId.FAKE: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(
            enabled=bool(active_injections),
            active_injections=list(active_injections),
        ),
    )
    return AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)


def minimal_pending_delivery(
    *,
    task_type: TaskType = TaskType.COLLECT,
    task_id: str = "task-contract-1",
    workflow_id: str = "wf-contract-1",
    attempt: int = 1,
) -> PendingDelivery:
    return PendingDelivery(
        message=TaskMessage(
            task_id=task_id,
            workflow_id=workflow_id,
            task_type=task_type,
            attempt=attempt,
            created_at=_FIXED_NOW,
            payload_reference="ref://payload/contract-1",
        ),
        stream="cartoon:tasks",
        consumer_group="workers",
        delivery_id=f"del-{task_id}",
        dequeued_at=_FIXED_NOW,
    )


def _seed_workflow_and_task(
    *,
    workflow_repo: ContractWorkflowRepo,
    delivery: PendingDelivery,
) -> None:
    from worker.state_mapping import WorkflowStateGuard

    wf_id = delivery.message.workflow_id
    task_type = delivery.message.task_type
    expected = WorkflowStateGuard.expected_state_for_task(task_type)
    if workflow_repo.get_workflow(wf_id) is None:
        workflow_repo.create_workflow(
            wf_id,
            initial_state=PersWorkflowState(expected.value),
        )
    else:
        workflow_repo.set_state(wf_id, expected.value)
    task = TaskRecord(
        task_id=delivery.message.task_id,
        workflow_id=wf_id,
        task_type=PersTaskType(task_type.value),
        attempt=delivery.message.attempt,
        status=TaskStatus.DISPATCHED,
        payload_reference=PayloadReference(ref_id="pl-contract-1", ref_kind="task_payload"),
        idempotency_key=f"idem-{delivery.message.task_id}",
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )
    workflow_repo.upsert_task(task)


def memory_worker_loop(
    *,
    config: AppConfig,
    handlers: Sequence[TaskHandler] | None = None,
    shared_fixture: MemoryWorkerFixture | None = None,
    consumer_name: str = "worker-contract-1",
) -> MemoryWorkerFixture:
    """Wire DefaultWorkerLoop with fakes per LLD §12.1."""
    from observability import get_logger, get_meter, get_tracer
    from providers import create_provider

    if shared_fixture is not None:
        txn = shared_fixture.txn
        workflow_repo = shared_fixture.workflow_repo
        artifact_repo = shared_fixture.artifact_repo
        idempotency_repo = shared_fixture.idempotency_repo
        task_lease_repo = shared_fixture.task_lease_repo
        queue = shared_fixture.queue
        engine = shared_fixture.engine
        recorded_resolutions = shared_fixture.recorded_resolutions
    else:
        txn = InMemoryTransactionManager()
        workflow_repo = ContractWorkflowRepo(transaction_manager=txn)
        artifact_repo = ContractArtifactRepo(transaction_manager=txn)
        idempotency_repo = ContractIdempotencyRepo(transaction_manager=txn)
        task_lease_repo = ContractTaskLeaseRepo(transaction_manager=txn)
        queue = FakeTaskQueue()
        engine = FakeWorkflowEngine()
        recorded_resolutions = []
    registry = create_task_handler_registry(
        handlers=list(handlers or [RecordingHandler(_task_type=TaskType.COLLECT)]),
    )
    orchestrator = create_idempotency_orchestrator(idempotency_repo=idempotency_repo)
    collector = SimpleNamespace(
        collect_stories=lambda **_kw: SimpleNamespace(
            candidates=[],
            stats=SimpleNamespace(total_fetched=0, accepted=0, rejected=0),
        ),
    )
    provider = create_provider(provider_id=ProviderId.FAKE, config=config)

    def model_provider_factory(agent_id: AgentId) -> object:
        return provider

    logger = get_logger()
    meter = get_meter()
    tracer = get_tracer()
    telemetry = RecordingWorkerTelemetry(logger=logger, meter=meter, tracer=tracer)

    from failure_injection.factory import build_failure_injection_registry

    class _NoopInjectionHook:
        def invoke(self, context: object | None = None) -> None:
            return None

    failure_injection = build_failure_injection_registry(config=config)
    for injection_id in (
        InjectionId.FINJ_WKR_PRE,
        InjectionId.FINJ_WKR_POST_AGENT,
        InjectionId.FINJ_WKR_POST_COMMIT,
        InjectionId.FINJ_WKR_PRE_ACK,
    ):
        failure_injection.register_hook(injection_id, _NoopInjectionHook())

    loop = create_worker_loop(
        config=config,
        loop_config=WorkerLoopConfig(
            stream="cartoon:tasks",
            consumer_group="workers",
            consumer_name=consumer_name,
            block_ms=0,
        ),
        registry=registry,
        task_queue=cast(object, queue),
        task_lease_repo=task_lease_repo,
        workflow_engine=cast(object, engine),
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        idempotency_orchestrator=orchestrator,
        transaction_manager=txn,
        failure_injection=failure_injection,
        collector=collector,
        topic_selection_agent=cast(
            object,
            SimpleNamespace(run=lambda **_kw: SimpleNamespace(
                outcome=__import__("agents.types", fromlist=["TopicSelectionOutcome"]).TopicSelectionOutcome.TOPIC_SELECTED,
                prompt_version="v1",
                selected_topic="topic",
            )),
        ),
        scenario_generation_agent=cast(
            object,
            SimpleNamespace(
                run=lambda **_kw: SimpleNamespace(
                    topic="topic",
                    premise="premise",
                    characters=(),
                    panels=(),
                    punchline="punch",
                    prompt_version="v1",
                ),
            ),
        ),
        critic_agent=cast(object, SimpleNamespace(run=lambda **_kw: object())),
        model_provider_factory=model_provider_factory,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )
  # Attach telemetry and resolution tracking to loop instance
    from worker.loop import DefaultWorkerLoop

    if isinstance(loop, DefaultWorkerLoop):
        loop.telemetry = telemetry
        loop._recorded_resolutions = recorded_resolutions

    if shared_fixture is None:
        default_delivery = minimal_pending_delivery()
        _seed_workflow_and_task(workflow_repo=workflow_repo, delivery=default_delivery)

    return MemoryWorkerFixture(
        loop=loop,
        queue=queue,
        engine=engine,
        txn=txn,
        idempotency_repo=idempotency_repo,
        workflow_repo=workflow_repo,
        artifact_repo=artifact_repo,
        task_lease_repo=task_lease_repo,
        recorded_resolutions=recorded_resolutions,
    )


def public_export_names() -> frozenset[str]:
    import worker

    return frozenset(worker.__all__)
