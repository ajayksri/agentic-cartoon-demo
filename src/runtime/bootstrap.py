"""Shared bootstrap wiring and connection settings (LLD §5–§6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
from typing import Any

from config.types import AppConfig
from failure_injection import configure_failure_injection, create_failure_injection_registry
from failure_injection.protocols import FailureInjectionRegistry
from observability import configure_observability, get_logger, get_meter, get_tracer
from persistence.bootstrap import ConnectionSettings, PersistenceBundle, PersistenceStackOptions
from task_queue.errors import TaskQueueConnectionError
from task_queue.connection import RedisConnectionManager
from task_queue.factory import TaskQueueFactory
from task_queue.protocols import TaskQueue
from workflow.protocols import WorkflowEngine, create_workflow_engine

from .errors import DependencyWiringError
from .hooks import register_production_hooks
from .messages import bootstrap_persistence_message, bootstrap_queue_message
from .queue_adapter import QueueBoundaryLoggerAdapter
from .settings import build_observability_settings
from .telemetry import RecordingRuntimeTelemetry, RuntimeTelemetry
from .types import ProcessEntryPoint, WiredDependencies

PersistenceFactory = Callable[..., PersistenceBundle]
QueueFactory = Callable[..., TaskQueue]
WorkflowFactory = Callable[..., WorkflowEngine]


@dataclass
class BootstrapContext:
    """Internal collaborators shared across process wiring (not public)."""

    entry: ProcessEntryPoint
    config: AppConfig
    bundle: PersistenceBundle
    task_queue: TaskQueue
    redis_connection_manager: RedisConnectionManager
    workflow_engine: WorkflowEngine
    failure_injection: FailureInjectionRegistry
    logger: object
    meter: object
    tracer: object
    telemetry: RuntimeTelemetry
    wired: WiredDependencies
    reconciliation_scheduler: object | None = None
    coordinator_shutdown: threading.Event | None = None


class ConnectionSettingsBuilder:
    """Resolve persistence connection settings from AppConfig."""

    @staticmethod
    def from_app_config(config: AppConfig) -> ConnectionSettings:
        pg = config.infrastructure.postgres
        user = config.resolve_credential(pg.user_env)
        password = config.resolve_credential(pg.password_env)
        return ConnectionSettings(
            host=pg.host,
            port=pg.port,
            database=pg.database,
            user=user,
            password=password,
        )


class SharedBootstrap:
    """Common bootstrap steps shared by all process entry kinds."""

    def wire_common(
        self,
        *,
        entry: ProcessEntryPoint,
        config: AppConfig,
        telemetry: RuntimeTelemetry | None = None,
        persistence_factory: PersistenceFactory | None = None,
        queue_factory: QueueFactory | None = None,
        workflow_factory: WorkflowFactory | None = None,
        failure_injection_factory: Any | None = None,
        connection_manager: RedisConnectionManager | None = None,
    ) -> BootstrapContext:
        observability_settings = build_observability_settings(entry=entry, config=config)

        if telemetry is not None and callable(getattr(telemetry, "configure", None)):
            telemetry.configure(observability_settings)
        else:
            configure_observability(settings=observability_settings)
            if isinstance(telemetry, RecordingRuntimeTelemetry):
                telemetry.record_configure_observability()

        logger = get_logger()
        meter = get_meter()
        tracer = get_tracer()

        if failure_injection_factory is not None:
            failure_injection_factory.configure()
            registry: FailureInjectionRegistry = failure_injection_factory
        else:
            registry = create_failure_injection_registry(config)
            register_production_hooks(registry, config=config)
            configure_failure_injection(registry)

        try:
            if persistence_factory is not None:
                bundle = persistence_factory(config=config, entry=entry)
            else:
                from persistence.bootstrap import create_persistence_stack

                bundle = create_persistence_stack(
                    ConnectionSettingsBuilder.from_app_config(config),
                    options=PersistenceStackOptions(health_check_on_bootstrap=True),
                )
        except Exception as exc:
            pg = config.infrastructure.postgres
            raise DependencyWiringError(
                bootstrap_persistence_message(host=pg.host, port=pg.port),
                entry=entry,
                dependency="persistence",
            ) from exc

        adapter = QueueBoundaryLoggerAdapter(logger, meter)

        redis_cm = connection_manager or RedisConnectionManager.from_app_config(config)

        try:
            if queue_factory is not None:
                queue = queue_factory(
                    config=config,
                    adapter=adapter,
                    connection_manager=redis_cm,
                )
            else:
                factory = TaskQueueFactory(
                    boundary_logger=adapter,
                    connection_manager=redis_cm,
                )
                queue = factory.create(config)
        except TaskQueueConnectionError as exc:
            redis_cfg = config.infrastructure.redis
            raise DependencyWiringError(
                bootstrap_queue_message(host=redis_cfg.host, port=redis_cfg.port),
                entry=entry,
                dependency="task_queue",
            ) from exc
        except Exception as exc:
            redis_cfg = config.infrastructure.redis
            raise DependencyWiringError(
                bootstrap_queue_message(host=redis_cfg.host, port=redis_cfg.port),
                entry=entry,
                dependency="task_queue",
            ) from exc

        workflow_kwargs = {
            "config": config,
            "workflow_repo": bundle.workflow_repo,
            "artifact_repo": bundle.artifact_repo,
            "outbox_repo": bundle.outbox_repo,
            "transaction_manager": bundle.transaction_manager,
        }
        if workflow_factory is not None:
            engine = workflow_factory(**workflow_kwargs)
        else:
            engine = create_workflow_engine(**workflow_kwargs)

        runtime_telemetry = telemetry or RuntimeTelemetry(
            logger=logger,
            meter=meter,
            process_kind=entry.kind,
        )

        wired = WiredDependencies(
            entry=entry,
            config=config,
            workflow_engine=engine,
            task_queue=queue,
        )

        return BootstrapContext(
            entry=entry,
            config=config,
            bundle=bundle,
            task_queue=queue,
            redis_connection_manager=redis_cm,
            workflow_engine=engine,
            failure_injection=registry,
            logger=logger,
            meter=meter,
            tracer=tracer,
            telemetry=runtime_telemetry,
            wired=wired,
        )
