"""API process wiring (LLD §10.1)."""

from __future__ import annotations

from collections.abc import Callable

from api import create_api_router
from api.protocols import ApiDependencies

from ..bootstrap import BootstrapContext
from ..http_server import TransactionMutatingContext
from ..probes import PostgresReadinessProbe, RedisReadinessProbe
from ..types import WiredDependencies

RouterFactory = Callable[..., object]


class ApiProcessWiring:
    """Builds ApiDependencies, readiness probes, and API router for the API entry."""

    def wire(
        self,
        ctx: BootstrapContext,
        *,
        router_factory: RouterFactory | None = None,
    ) -> BootstrapContext:
        probes = (
            PostgresReadinessProbe(ctx.bundle.pool_manager),
            RedisReadinessProbe(ctx.redis_connection_manager),
        )
        deps = ApiDependencies(
            config=ctx.config,
            workflow_engine=ctx.workflow_engine,
            readiness_probes=probes,
            service_name=ctx.entry.service_name,
        )
        mutating = TransactionMutatingContext(ctx.bundle.transaction_manager)

        if router_factory is not None:
            router = router_factory(deps=deps, mutating_context=mutating)
        else:
            router = create_api_router(deps=deps, mutating_context=mutating)

        ctx.wired = WiredDependencies(
            entry=ctx.entry,
            config=ctx.config,
            workflow_engine=ctx.workflow_engine,
            task_queue=ctx.task_queue,
            api_router=router,
        )
        return ctx
