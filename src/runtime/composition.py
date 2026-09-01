"""Composition root — config load and process-specific wiring (LLD §8)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Multi-process architecture — API, coordinator, and
# worker run as separate OS processes coordinated only via PostgreSQL and Redis.

from __future__ import annotations

from typing import TYPE_CHECKING

from config.errors import ConfigError
from config.loader import load_config
from config.types import AppConfig, ConfigSource
from observability import get_tracer

from .bootstrap import BootstrapContext, PersistenceFactory, SharedBootstrap
from .errors import BootstrapError, DependencyWiringError, UnsupportedProcessKindError
from .settings import WorkerProcessConfig
from .types import BootstrapResult, CoordinatorLoopConfig, ProcessEntryPoint, ProcessKind, WiredDependencies
from .wiring.api import ApiProcessWiring
from .wiring.coordinator import CoordinatorProcessWiring
from .wiring.worker import WorkerProcessWiring

if TYPE_CHECKING:
    from persistence.bootstrap import PersistenceBundle
    from task_queue.protocols import TaskQueue
    from worker.protocols import WorkerLoop
    from workflow.protocols import WorkflowEngine


class DefaultCompositionRoot:
    """Loads config once and wires collaborators per process entry kind."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._context: BootstrapContext | None = None

    @property
    def config(self) -> AppConfig:
        return self._config

    def bootstrap(
        self,
        entry: ProcessEntryPoint,
        *,
        worker_config: WorkerProcessConfig | None = None,
        loop_config: CoordinatorLoopConfig | None = None,
    ) -> BootstrapResult:
        if self._context is not None:
            self._teardown_partial(self._context)

        try:
            tracer = get_tracer()
            with tracer.start_span(
                "runtime.bootstrap",
                attributes={"process_kind": _process_kind_value(entry)},
            ):
                ctx = SharedBootstrap().wire_common(entry=entry, config=self._config)
                ctx = _wire_process_kind(
                    ctx,
                    entry=entry,
                    worker_config=worker_config,
                    loop_config=loop_config,
                )
                self._context = ctx
                return BootstrapResult(
                    entry=entry,
                    config_loaded=True,
                    observability_configured=True,
                    failure_injection_configured=True,
                    message=f"bootstrap complete for {entry.service_name}",
                )
        except ConfigError:
            raise
        except DependencyWiringError:
            raise
        except UnsupportedProcessKindError:
            raise
        except Exception as exc:
            raise BootstrapError(
                f"bootstrap failed for {entry.service_name}",
                entry=entry,
            ) from exc

    def wired_dependencies(self) -> WiredDependencies:
        if self._context is None:
            raise BootstrapError("bootstrap not completed")
        return self._context.wired

    def _teardown_partial(self, ctx: BootstrapContext) -> None:
        """Close prior bootstrap handles before re-bootstrap (MOD-RT-INV-010)."""
        try:
            ctx.redis_connection_manager.close()
        except Exception:
            pass
        try:
            ctx.bundle.pool_manager.close()
        except Exception:
            pass


def create_composition_root(*, source: ConfigSource | None = None) -> DefaultCompositionRoot:
    """Load config and return a composition root ready for bootstrap()."""
    config = load_config(source)
    return DefaultCompositionRoot(config)


def _wire_process_kind(
    ctx: BootstrapContext,
    *,
    entry: ProcessEntryPoint,
    worker_config: WorkerProcessConfig | None,
    loop_config: CoordinatorLoopConfig | None = None,
) -> BootstrapContext:
    kind = entry.kind
    if kind == ProcessKind.API:
        return ApiProcessWiring().wire(ctx)
    if kind == ProcessKind.COORDINATOR:
        return CoordinatorProcessWiring().wire(ctx, loop_config=loop_config)
    if kind == ProcessKind.WORKER:
        return WorkerProcessWiring().wire(
            ctx,
            worker_config=worker_config or WorkerProcessConfig(),
        )
    raise UnsupportedProcessKindError(
        f"unsupported process kind: {kind!r}",
        kind=kind if isinstance(kind, ProcessKind) else ProcessKind.API,
    )


def _process_kind_value(entry: ProcessEntryPoint) -> str:
    kind = entry.kind
    if isinstance(kind, ProcessKind):
        return kind.value
    return str(kind)


def _bootstrap_for_tests(
    *,
    entry: ProcessEntryPoint,
    config: AppConfig,
    persistence: PersistenceBundle | None = None,
    task_queue: TaskQueue | None = None,
    workflow_engine: WorkflowEngine | None = None,
    worker_loop: WorkerLoop | None = None,
    telemetry: object | None = None,
    call_order: object | None = None,
    persistence_error: BaseException | None = None,
) -> WiredDependencies:
    """Internal contract-test seam — inject fakes without live infrastructure (LLD §21.3)."""
    from unittest.mock import MagicMock

    from runtime.fakes.persistence import build_fake_persistence_bundle
    from runtime.fakes.task_queue import FakeConnectionManager
    from runtime.telemetry import RecordingRuntimeTelemetry
    from runtime.wiring.worker import WorkerProductionDependencies

    def _record(name: str) -> None:
        if call_order is not None and hasattr(call_order, "record"):
            call_order.record(name)  # type: ignore[union-attr]

    if persistence_error is not None:

        def _raising_persistence(**_kwargs: object) -> PersistenceBundle:
            raise persistence_error

        persistence_factory: PersistenceFactory | None = _raising_persistence  # type: ignore[assignment]
    else:
        bundle = persistence or build_fake_persistence_bundle()
        persistence_factory = lambda **_kwargs: bundle  # noqa: E731

    queue = task_queue or MagicMock()
    engine = workflow_engine or MagicMock()
    finj = MagicMock()

    def _configure_finj() -> None:
        _record("configure_failure_injection")

    finj.configure = _configure_finj

    runtime_telemetry = telemetry
    if runtime_telemetry is None:
        runtime_telemetry = MagicMock()
        runtime_telemetry.configure = MagicMock()

    ctx = SharedBootstrap().wire_common(
        entry=entry,
        config=config,
        telemetry=runtime_telemetry,  # type: ignore[arg-type]
        persistence_factory=persistence_factory,
        queue_factory=lambda **_kwargs: queue,
        workflow_factory=lambda **_kwargs: engine,
        failure_injection_factory=finj,
        connection_manager=FakeConnectionManager(),  # type: ignore[arg-type]
    )

    if entry.kind == ProcessKind.API:
        ctx = ApiProcessWiring().wire(
            ctx,
            router_factory=lambda **_kwargs: MagicMock(),
        )
    elif entry.kind == ProcessKind.COORDINATOR:
        ctx = CoordinatorProcessWiring().wire(ctx)
    elif entry.kind == ProcessKind.WORKER:

        def _worker_loop_factory(**_kwargs: object) -> WorkerLoop:
            _record("worker_loop_start")
            return worker_loop or MagicMock()  # type: ignore[return-value]

        ctx = WorkerProcessWiring().wire(
            ctx,
            worker_dependencies_factory=lambda **_kwargs: WorkerProductionDependencies(
                registry=MagicMock(),
                idempotency_orchestrator=MagicMock(),
                collector=MagicMock(),
                topic_selection_agent=MagicMock(),
                scenario_generation_agent=MagicMock(),
                critic_agent=MagicMock(),
                model_provider_factory=MagicMock(),
            ),
            worker_loop_factory=_worker_loop_factory,
        )
    else:
        raise UnsupportedProcessKindError(
            f"unsupported process kind: {entry.kind!r}",
            kind=entry.kind if isinstance(entry.kind, ProcessKind) else ProcessKind.API,
        )

    if isinstance(runtime_telemetry, RecordingRuntimeTelemetry):
        runtime_telemetry.record_loop_start()

    return ctx.wired
