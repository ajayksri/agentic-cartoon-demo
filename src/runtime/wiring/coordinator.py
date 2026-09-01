"""Coordinator process wiring (LLD §12)."""

from __future__ import annotations

import threading

from ..bootstrap import BootstrapContext
from ..outbox import create_outbox_publisher_loop
from ..reconciliation import ReconciliationScheduler
from ..types import CoordinatorLoopConfig, WiredDependencies


class CoordinatorProcessWiring:
    """Assembles outbox publisher and reconciliation scheduler handles."""

    def wire(
        self,
        ctx: BootstrapContext,
        *,
        loop_config: CoordinatorLoopConfig | None = None,
        shutdown: threading.Event | None = None,
    ) -> BootstrapContext:
        coordinator_loop = loop_config or CoordinatorLoopConfig()
        shutdown_event = shutdown or threading.Event()

        outbox_publisher = create_outbox_publisher_loop(
            config=ctx.config,
            publisher_config=coordinator_loop.outbox,
            outbox_repo=ctx.bundle.outbox_repo,
            workflow_repo=ctx.bundle.workflow_repo,
            task_queue=ctx.task_queue,
            workflow_engine=ctx.workflow_engine,
            failure_injection=ctx.failure_injection,
            logger=ctx.logger,  # type: ignore[arg-type]
            meter=ctx.meter,  # type: ignore[arg-type]
            tracer=ctx.tracer,  # type: ignore[arg-type]
            shutdown=shutdown_event,
        )
        reconciliation_scheduler = ReconciliationScheduler(
            config=ctx.config,
            workflow_engine=ctx.workflow_engine,
            loop_config=coordinator_loop,
            telemetry=ctx.telemetry,
            shutdown=shutdown_event,
        )

        ctx.coordinator_shutdown = shutdown_event
        ctx.reconciliation_scheduler = reconciliation_scheduler
        ctx.wired = WiredDependencies(
            entry=ctx.entry,
            config=ctx.config,
            workflow_engine=ctx.workflow_engine,
            task_queue=ctx.task_queue,
            outbox_publisher=outbox_publisher,
        )
        return ctx
