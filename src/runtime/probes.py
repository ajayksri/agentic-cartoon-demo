"""Readiness probes for API process wiring (LLD §9)."""

from __future__ import annotations

import concurrent.futures
from typing import Protocol

from api.types import DependencyCheck, DependencyCheckStatus

from .constants import PROBE_NAME_POSTGRES, PROBE_NAME_REDIS, READINESS_PROBE_TIMEOUT_SECONDS


class _HealthCheckable(Protocol):
    def health_check(self) -> None: ...


class _Pingable(Protocol):
    def ping(self) -> None: ...


def _run_with_timeout(fn: object, *, timeout_seconds: float) -> bool:
    """Run callable in a worker thread; return False on timeout or any error."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)  # type: ignore[arg-type]
        try:
            future.result(timeout=timeout_seconds)
            return True
        except Exception:
            return False


class PostgresReadinessProbe:
    """Postgres readiness via persistence pool health_check."""

    def __init__(self, pool_manager: _HealthCheckable) -> None:
        self._pool_manager = pool_manager

    @property
    def name(self) -> str:
        return PROBE_NAME_POSTGRES

    def check(self) -> DependencyCheck:
        ok = _run_with_timeout(
            self._pool_manager.health_check,
            timeout_seconds=READINESS_PROBE_TIMEOUT_SECONDS,
        )
        if ok:
            return DependencyCheck(
                name=self.name,
                status=DependencyCheckStatus.OK,
                detail=None,
            )
        return DependencyCheck(
            name=self.name,
            status=DependencyCheckStatus.FAIL,
            detail="postgres_unreachable",
        )


class RedisReadinessProbe:
    """Redis readiness via connection manager ping."""

    def __init__(self, connection_manager: _Pingable) -> None:
        self._connection_manager = connection_manager

    @property
    def name(self) -> str:
        return PROBE_NAME_REDIS

    def check(self) -> DependencyCheck:
        ok = _run_with_timeout(
            self._connection_manager.ping,
            timeout_seconds=READINESS_PROBE_TIMEOUT_SECONDS,
        )
        if ok:
            return DependencyCheck(
                name=self.name,
                status=DependencyCheckStatus.OK,
                detail=None,
            )
        return DependencyCheck(
            name=self.name,
            status=DependencyCheckStatus.FAIL,
            detail="redis_unreachable",
        )
