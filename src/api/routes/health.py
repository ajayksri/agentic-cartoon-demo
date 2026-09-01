"""Health and readiness route handlers."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Liveness and readiness probes — /health and /ready
# let orchestrators (Kubernetes, load balancers) route traffic and restart unhealthy pods.

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from ..constants import ROUTE_HEALTH, ROUTE_READY, SPAN_HEALTH, SPAN_READY
from ..protocols import ApiDependencies, ReadinessProbe
from ..telemetry import get_active_telemetry
from ..types import (
    DependencyCheck,
    DependencyCheckStatus,
    HealthResponse,
    HealthStatus,
    ReadinessResponse,
    ReadinessStatus,
)


class ReadinessAggregator:
    """Aggregate readiness probe results into a single response."""

    def __init__(self, probes: Sequence[ReadinessProbe]) -> None:
        self._probes = probes

    def aggregate(self) -> ReadinessResponse:
        checks: list[DependencyCheck] = []
        for probe in self._probes:
            try:
                check = probe.check()
            except Exception:
                check = DependencyCheck(
                    name=probe.name,
                    status=DependencyCheckStatus.FAIL,
                    detail="probe_error",
                )
            checks.append(check)

        all_ok = all(check.status == DependencyCheckStatus.OK for check in checks) if checks else True
        return ReadinessResponse(
            status=ReadinessStatus.READY if all_ok else ReadinessStatus.NOT_READY,
            checks=tuple(checks),
            timestamp=datetime.now(tz=UTC),
        )


def resolve_service_name(*, deps: ApiDependencies) -> str:
    """Resolve health probe service identity (LLD-API-005)."""
    if deps.service_name:
        return deps.service_name
    return "cartoon-demo-api"


async def handle_health(*, deps: ApiDependencies) -> HealthResponse:
    """GET /health — process liveness probe (ACD-API-006)."""
    telemetry = get_active_telemetry()
    span = telemetry.start_route_span(SPAN_HEALTH)
    with span:
        telemetry.emit_request_success(
            route_id=ROUTE_HEALTH,
            http_method="GET",
            status_code=200,
        )
        return HealthResponse(
            status=HealthStatus.OK,
            service_name=resolve_service_name(deps=deps),
            timestamp=datetime.now(tz=UTC),
        )


async def handle_readiness(*, deps: ApiDependencies) -> ReadinessResponse:
    """GET /ready — dependency readiness probe (ACD-API-006)."""
    telemetry = get_active_telemetry()
    span = telemetry.start_route_span(SPAN_READY)
    with span:
        response = ReadinessAggregator(deps.readiness_probes).aggregate()
        status_code = 200 if response.status == ReadinessStatus.READY else 503
        telemetry.emit_request_success(
            route_id=ROUTE_READY,
            http_method="GET",
            status_code=status_code,
        )
        return response
