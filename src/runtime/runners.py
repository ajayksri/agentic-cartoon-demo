"""Process runners and console entry points (LLD §14, §17)."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from config.types import ConfigSource, TaskType

from .bootstrap import BootstrapContext
from .composition import DefaultCompositionRoot, create_composition_root
from .constants import (
    DEFAULT_HTTP_SHUTDOWN_GRACE_SECONDS,
    DEFAULT_WORKER_ROLE,
    DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS,
)
from .http_server import ApiHttpServer
from .errors import ProcessShutdownError
from .settings import ApiServerConfig, WorkerProcessConfig
from .shutdown import ShutdownCoordinator
from .types import (
    API_ENTRY,
    COORDINATOR_ENTRY,
    WORKER_ENTRY,
    CoordinatorLoopConfig,
)

if TYPE_CHECKING:
    from worker.protocols import WorkerLoop


def run_api_process(
    *,
    source: ConfigSource | None = None,
    http_server: ApiHttpServer | None = None,
) -> None:
    """Bootstrap and run the API process until shutdown (LLD §14.1)."""
    root = create_composition_root(source=source)
    root.bootstrap(API_ENTRY)
    ctx = _require_context(root)
    deps = root.wired_dependencies()

    ctx.telemetry.log_process_started(kind=API_ENTRY.kind, service_name=API_ENTRY.service_name)
    shutdown = ShutdownCoordinator.register(
        API_ENTRY,
        grace_seconds=DEFAULT_HTTP_SHUTDOWN_GRACE_SECONDS,
    )
    try:
        server = http_server or ApiHttpServer()
        server.serve(
            router=deps.api_router,
            config=ApiServerConfig(),
            shutdown=shutdown,
        )
    finally:
        ctx.telemetry.log_shutdown_started(
            kind=API_ENTRY.kind,
            service_name=API_ENTRY.service_name,
        )
        _teardown_connections(ctx)
        ctx.telemetry.log_shutdown_complete(
            kind=API_ENTRY.kind,
            service_name=API_ENTRY.service_name,
        )
        _clear_context(root)


def run_coordinator_process(
    *,
    source: ConfigSource | None = None,
    loop_config: CoordinatorLoopConfig | None = None,
) -> None:
    """Bootstrap and run coordinator background loops until shutdown (LLD §12)."""
    root = create_composition_root(source=source)
    root.bootstrap(COORDINATOR_ENTRY, loop_config=loop_config)
    ctx = _require_context(root)
    deps = root.wired_dependencies()

    publisher = deps.outbox_publisher
    reconciler = ctx.reconciliation_scheduler
    if publisher is None or reconciler is None:
        raise RuntimeError("coordinator wiring incomplete")

    grace_seconds = (loop_config or CoordinatorLoopConfig()).outbox.shutdown_grace_seconds
    ctx.telemetry.log_process_started(
        kind=COORDINATOR_ENTRY.kind,
        service_name=COORDINATOR_ENTRY.service_name,
    )

    publisher_thread = threading.Thread(
        target=publisher.run,
        daemon=True,
        name="outbox-publisher",
    )
    reconciler_thread = threading.Thread(
        target=reconciler.run,
        daemon=True,
        name="reconciliation",
    )
    publisher_thread.start()
    reconciler_thread.start()

    shutdown = ShutdownCoordinator.register(
        COORDINATOR_ENTRY,
        grace_seconds=grace_seconds,
    )
    try:
        ShutdownCoordinator.wait_for_signal(shutdown)
        publisher.stop()
        reconciler.stop()
        publisher_thread.join(timeout=grace_seconds)
        reconciler_thread.join(timeout=grace_seconds)
    finally:
        ctx.telemetry.log_shutdown_started(
            kind=COORDINATOR_ENTRY.kind,
            service_name=COORDINATOR_ENTRY.service_name,
        )
        _teardown_connections(ctx)
        ctx.telemetry.log_shutdown_complete(
            kind=COORDINATOR_ENTRY.kind,
            service_name=COORDINATOR_ENTRY.service_name,
        )
        _clear_context(root)


def run_worker_process(
    *,
    source: ConfigSource | None = None,
    worker_role: TaskType | None = None,
) -> None:
    """Bootstrap and run the worker process until shutdown (LLD §13, §14)."""
    root = create_composition_root(source=source)
    role = worker_role or DEFAULT_WORKER_ROLE
    worker_config = WorkerProcessConfig(worker_role=role)
    root.bootstrap(WORKER_ENTRY, worker_config=worker_config)
    ctx = _require_context(root)
    deps = root.wired_dependencies()

    worker_loop = deps.worker_loop
    if worker_loop is None:
        raise RuntimeError("worker wiring incomplete")

    loop_overrides = worker_config.loop_config_overrides
    shutdown_grace = (
        loop_overrides.shutdown_grace_seconds
        if loop_overrides is not None
        else DEFAULT_WORKER_SHUTDOWN_GRACE_SECONDS
    )

    ctx.telemetry.log_process_started(
        kind=WORKER_ENTRY.kind,
        service_name=WORKER_ENTRY.service_name,
    )

    worker_thread = threading.Thread(
        target=worker_loop.run,
        daemon=False,
        name="worker-loop",
    )
    worker_thread.start()

    shutdown = ShutdownCoordinator.register(
        WORKER_ENTRY,
        grace_seconds=shutdown_grace,
    )
    shutdown_error: ProcessShutdownError | None = None
    try:
        ShutdownCoordinator.wait_for_signal(shutdown)
        worker_loop.stop()
        try:
            ShutdownCoordinator.join_with_grace(
                worker_thread,
                grace_seconds=shutdown_grace,
                entry=WORKER_ENTRY,
            )
        except ProcessShutdownError as exc:
            shutdown_error = exc
    finally:
        ctx.telemetry.log_shutdown_started(
            kind=WORKER_ENTRY.kind,
            service_name=WORKER_ENTRY.service_name,
        )
        _teardown_connections(ctx)
        ctx.telemetry.log_shutdown_complete(
            kind=WORKER_ENTRY.kind,
            service_name=WORKER_ENTRY.service_name,
        )
        _clear_context(root)
    if shutdown_error is not None:
        raise shutdown_error


def run_worker_shutdown_sequence(
    *,
    worker_loop: WorkerLoop,
    teardown: Callable[[], None],
) -> None:
    """Stop worker loop before connection teardown (RT-TC-017)."""
    worker_loop.stop()
    teardown()


def _parse_worker_role_from_argv_or_env() -> TaskType | None:
    """Map deployment --role flag or CARTOON_DEMO_WORKER_ROLE env to TaskType."""
    for index, argument in enumerate(sys.argv):
        if argument == "--role" and index + 1 < len(sys.argv):
            return TaskType(sys.argv[index + 1])
        if argument.startswith("--role="):
            return TaskType(argument.split("=", 1)[1])

    env_role = os.environ.get("CARTOON_DEMO_WORKER_ROLE")
    if env_role:
        return TaskType(env_role)
    return None


def _entry_api() -> None:
    raise SystemExit(run_api_process() or 0)


def _entry_coordinator() -> None:
    raise SystemExit(run_coordinator_process() or 0)


def _entry_worker() -> None:
    role = _parse_worker_role_from_argv_or_env()
    raise SystemExit(run_worker_process(worker_role=role) or 0)


def _require_context(root: DefaultCompositionRoot) -> BootstrapContext:
    ctx = root._context  # noqa: SLF001
    if ctx is None:
        raise RuntimeError("bootstrap context unavailable")
    return ctx


def _teardown_connections(ctx: BootstrapContext) -> None:
    try:
        ctx.redis_connection_manager.close()
    except Exception:
        pass
    try:
        ctx.bundle.pool_manager.close()
    except Exception:
        pass


def _clear_context(root: DefaultCompositionRoot) -> None:
    root._context = None  # noqa: SLF001
