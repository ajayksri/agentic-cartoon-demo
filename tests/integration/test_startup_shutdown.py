"""IT-INT-009 / IT-INT-010 / IT-INT-011 — startup, readiness, shutdown (INT-002).

Public surfaces only: ``api``, ``runtime``, ``config``. Protocol-conformant
readiness doubles live in this module (integration-test-plan §2.4).
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from api import (
    PATH_HEALTH,
    PATH_READY,
    ApiDependencies,
    DependencyCheck,
    DependencyCheckStatus,
    HealthStatus,
    ReadinessStatus,
    create_api_router,
)
from config.errors import ConfigError
from config.types import ConfigSource
from runtime import (
    create_composition_root,
    run_api_process,
    run_coordinator_process,
    run_worker_process,
)
from tests.integration import helpers as harness

pytestmark = [pytest.mark.integration, pytest.mark.it_int]


@dataclass
class _FailingProbe:
    """ReadinessProbe double that reports infra down (never raises)."""

    name: str
    detail: str = "unreachable"

    def check(self) -> DependencyCheck:
        return DependencyCheck(
            name=self.name,
            status=DependencyCheckStatus.FAIL,
            detail=self.detail,
        )


@dataclass
class _HealthyProbe:
    """ReadinessProbe double that reports OK."""

    name: str

    def check(self) -> DependencyCheck:
        return DependencyCheck(name=self.name, status=DependencyCheckStatus.OK, detail=None)


class _StubWorkflowEngine:
    """Minimal workflow collaborator; health/ready routes do not invoke it."""


def _make_test_client(router: object) -> Any:
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)  # type: ignore[arg-type]
    return TestClient(app)


def _api_deps_with_probes(
    config: Any,
    probes: tuple[Any, ...],
) -> ApiDependencies:
    return ApiDependencies(
        config=config,
        workflow_engine=_StubWorkflowEngine(),  # type: ignore[arg-type]
        readiness_probes=probes,
        service_name="cartoon-demo-api",
    )


@pytest.mark.it_int("IT-INT-009")
def test_it_int_009_health_alive_ready_not_when_infra_probes_fail(
    integration_app_config: Any,
) -> None:
    """IT-INT-009: /health alive when deps down; /ready not ready (ACD-API-006).

    Postgres/Redis-down is modeled via failing ReadinessProbe doubles injected
    through the public ``ApiDependencies.readiness_probes`` seam (CG-API-010).
    """
    deps = _api_deps_with_probes(
        integration_app_config,
        (
            _FailingProbe("postgres", detail="connection_refused"),
            _FailingProbe("redis", detail="connection_refused"),
        ),
    )
    client = _make_test_client(create_api_router(deps=deps))

    health = client.get(PATH_HEALTH)
    assert health.status_code == 200
    assert health.json()["status"] == HealthStatus.OK.value

    ready = client.get(PATH_READY)
    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == ReadinessStatus.NOT_READY.value
    names = {check["name"] for check in body["checks"]}
    assert "postgres" in names
    assert "redis" in names
    assert all(check["status"] == DependencyCheckStatus.FAIL.value for check in body["checks"])


@pytest.mark.it_int("IT-INT-009")
def test_it_int_009_ready_ok_when_probes_healthy(integration_app_config: Any) -> None:
    """IT-INT-009 complement: /ready is ready when probes report OK."""
    deps = _api_deps_with_probes(
        integration_app_config,
        (_HealthyProbe("postgres"), _HealthyProbe("redis")),
    )
    client = _make_test_client(create_api_router(deps=deps))

    ready = client.get(PATH_READY)
    assert ready.status_code == 200
    assert ready.json()["status"] == ReadinessStatus.READY.value


def _write_malformed_config(path: Path) -> Path:
    path.write_text("infrastructure: [this is not valid app config]\n", encoding="utf-8")
    return path


@pytest.mark.it_int("IT-INT-010")
def test_it_int_010_malformed_config_fails_before_bind(tmp_path: Path) -> None:
    """IT-INT-010: malformed config → composition load fails before bind (ACD-OPS-010)."""
    bad = _write_malformed_config(tmp_path / "bad.yaml")
    source = ConfigSource(path=bad)

    with pytest.raises(ConfigError):
        create_composition_root(source=source)


@pytest.mark.it_int("IT-INT-010")
@pytest.mark.parametrize(
    ("runner", "entry_label"),
    [
        (run_api_process, "api"),
        (run_coordinator_process, "coordinator"),
        (run_worker_process, "worker"),
    ],
)
def test_it_int_010_run_process_fail_fast_malformed_config(
    tmp_path: Path,
    runner: Any,
    entry_label: str,
) -> None:
    """IT-INT-010: each run_*_process fails fast on malformed config (no port bind)."""
    bad = _write_malformed_config(tmp_path / f"bad-{entry_label}.yaml")
    with pytest.raises(ConfigError):
        runner(source=ConfigSource(path=bad))


@pytest.mark.it_int("IT-INT-010")
def test_it_int_010_console_entry_nonzero_exit(tmp_path: Path) -> None:
    """IT-INT-010: cartoon-demo-api console entry exits non-zero before bind."""
    bad = _write_malformed_config(tmp_path / "bad-entry.yaml")
    env = os.environ.copy()
    env["CARTOON_CONFIG_PATH"] = str(bad)
    # Avoid inheriting a valid default config from the workspace cwd.
    proc = subprocess.run(
        [sys.executable, "-c", "from runtime.runners import _entry_api; _entry_api()"],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode != 0, proc.stderr


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _wait_http_ok(url: str, *, timeout_seconds: float = 30.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout_seconds
    last_exc: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200:
                return
        except BaseException as exc:  # noqa: BLE001 — poll until ready
            last_exc = exc
        time.sleep(0.2)
    raise TimeoutError(f"API did not become ready at {url}: {last_exc}")


@contextmanager
def _api_subprocess(
    *,
    config_path: Path,
    database_url: str,
    redis_url: str,
) -> Iterator[subprocess.Popen[str]]:
    """Spawn production API entry with harness env; terminate on exit."""
    postgres = harness.parse_database_url(database_url)
    harness.ensure_fake_provider_env()
    harness.sync_postgres_credential_env(postgres)

    env = os.environ.copy()
    env["CARTOON_CONFIG_PATH"] = str(config_path)
    env[harness.DATABASE_URL_ENV] = database_url
    env[harness.REDIS_URL_ENV] = redis_url
    env[harness.FAKE_API_KEY_ENV] = os.environ.get(
        harness.FAKE_API_KEY_ENV, harness.DEFAULT_FAKE_API_KEY
    )
    env[harness.POSTGRES_USER_ENV] = postgres.user
    env[harness.POSTGRES_PASSWORD_ENV] = postgres.password
    harness.ensure_subprocess_pythonpath(env)

    proc = subprocess.Popen(
        [sys.executable, "-c", "from runtime.runners import _entry_api; _entry_api()"],
        env=env,
        cwd=str(harness.REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.mark.it_int("IT-INT-011")
def test_it_int_011_sigterm_drains_api_cleanly(
    tmp_path: Path,
    integration_infra: dict[str, str],
    integration_schema: Path,
) -> None:
    """IT-INT-011: SIGTERM to API exits cleanly; HTTP stops (ACD-OPS-003).

    Requires live PostgreSQL + Redis (production bootstrap). Skips via
    ``integration_infra`` when absent — never silently passes.
    """
    _ = integration_schema
    if not _port_free("127.0.0.1", 8000):
        pytest.skip(
            "EXTERNAL_EVIDENCE_REQUIRED: default API port 8000 is busy; "
            "cannot bind cartoon-demo-api for SIGTERM drain test"
        )

    database_url = integration_infra[harness.DATABASE_URL_ENV]
    redis_url = integration_infra[harness.REDIS_URL_ENV]
    config_path = harness.write_temp_config_yaml(
        tmp_path / "cartoon.sigterm.yaml",
        database_url=database_url,
        redis_url=redis_url,
    )

    base = harness.http_client_base_url(host="127.0.0.1", port=8000)
    with _api_subprocess(
        config_path=config_path,
        database_url=database_url,
        redis_url=redis_url,
    ) as proc:
        try:
            _wait_http_ok(f"{base}{PATH_HEALTH}", timeout_seconds=45.0)
        except TimeoutError:
            stdout, stderr = proc.communicate(timeout=5)
            pytest.fail(
                "API failed to start for IT-INT-011 "
                f"(exit={proc.returncode}): stdout={stdout!r} stderr={stderr!r}"
            )

        # In-flight probe: health is in-flight-friendly; issue request then SIGTERM.
        import httpx

        with httpx.Client(timeout=5.0) as client:
            inflight = client.get(f"{base}{PATH_HEALTH}")
            assert inflight.status_code == 200

        proc.send_signal(signal.SIGTERM)
        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("API did not exit within grace after SIGTERM")

        assert returncode == 0, (
            f"expected clean exit after SIGTERM, got {returncode}; "
            f"stderr={proc.stderr.read() if proc.stderr else ''}"
        )

    # Connections closed: subsequent HTTP must fail.
    import httpx

    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{base}{PATH_HEALTH}", timeout=1.0)
