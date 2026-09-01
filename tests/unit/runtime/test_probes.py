"""Unit tests for RT-005 — readiness probes."""

from __future__ import annotations

from api.types import DependencyCheckStatus

from runtime.constants import PROBE_NAME_POSTGRES, PROBE_NAME_REDIS, READINESS_PROBE_TIMEOUT_SECONDS
from runtime.fakes.persistence import FakePoolManager
from runtime.fakes.task_queue import FakeConnectionManager
from runtime.probes import PostgresReadinessProbe, RedisReadinessProbe


def test_postgres_probe_ok_when_health_check_succeeds() -> None:
    probe = PostgresReadinessProbe(FakePoolManager(health_ok=True))

    result = probe.check()

    assert probe.name == PROBE_NAME_POSTGRES
    assert result.status == DependencyCheckStatus.OK
    assert result.detail is None


def test_postgres_probe_fail_when_health_check_raises() -> None:
    probe = PostgresReadinessProbe(FakePoolManager(health_ok=False))

    result = probe.check()

    assert result.status == DependencyCheckStatus.FAIL
    assert result.detail == "postgres_unreachable"


def test_postgres_probe_fail_on_timeout() -> None:
    probe = PostgresReadinessProbe(
        FakePoolManager(
            health_ok=True,
            health_delay_seconds=READINESS_PROBE_TIMEOUT_SECONDS + 0.5,
        )
    )

    result = probe.check()

    assert result.status == DependencyCheckStatus.FAIL
    assert result.detail == "postgres_unreachable"


def test_redis_probe_ok_when_ping_succeeds() -> None:
    probe = RedisReadinessProbe(FakeConnectionManager(ping_ok=True))

    result = probe.check()

    assert probe.name == PROBE_NAME_REDIS
    assert result.status == DependencyCheckStatus.OK
    assert result.detail is None


def test_redis_probe_fail_when_ping_raises() -> None:
    probe = RedisReadinessProbe(FakeConnectionManager(ping_ok=False))

    result = probe.check()

    assert result.status == DependencyCheckStatus.FAIL
    assert result.detail == "redis_unreachable"


def test_probes_never_raise() -> None:
    postgres = PostgresReadinessProbe(FakePoolManager(health_ok=False))
    redis = RedisReadinessProbe(FakeConnectionManager(ping_ok=False))

    postgres.check()
    redis.check()
