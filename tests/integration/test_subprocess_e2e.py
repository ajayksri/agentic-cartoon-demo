"""INT-006 — production subprocess E2E (Wave 81-W5).

Spawns ``cartoon-demo-coordinator``, four ``cartoon-demo-worker`` roles, and
``cartoon-demo-api`` via public runtime console entry points with shared harness
config. No injectable worker doubles or forbidden internal imports
(interface-gaps §4.1 / PD-001).
"""

from __future__ import annotations

import ast
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from api import PATH_HEALTH, PATH_READY, PATH_WORKFLOW_BY_ID, PATH_WORKFLOWS
from tests.integration import helpers as harness
from workflow.types import WorkflowState

pytestmark = [pytest.mark.integration, pytest.mark.it_int]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_ROLES = (
    "COLLECT",
    "SELECT_TOPIC",
    "GENERATE_SCENARIO",
    "REVIEW_SCENARIO",
)
_TASK_STREAMS = (
    "cartoon:tasks:collect",
    "cartoon:tasks:select_topic",
    "cartoon:tasks:generate_scenario",
    "cartoon:tasks:review_scenario",
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "runtime.wiring",
    "worker.handlers",
    "runtime.composition._bootstrap_for_tests",
)


def _reset_task_streams(redis_url: str) -> None:
    """Drop stale Redis task streams so prior crashed workers do not block PEL delivery."""
    import redis

    client = redis.Redis.from_url(redis_url)
    for stream in _TASK_STREAMS:
        client.delete(stream)


def _assert_public_interface_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                    assert not alias.name.startswith(prefix), alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                assert not node.module.startswith(prefix), node.module


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _wait_http_ok(url: str, *, timeout_seconds: float = 45.0) -> None:
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
    raise TimeoutError(f"HTTP endpoint did not become ready at {url}: {last_exc}")


def _build_process_env(
    *,
    config_path: Path,
    database_url: str,
    redis_url: str,
) -> dict[str, str]:
    postgres = harness.parse_database_url(database_url)
    harness.ensure_fake_provider_env()
    harness.sync_postgres_credential_env(postgres)

    env = os.environ.copy()
    env["CARTOON_CONFIG_PATH"] = str(config_path)
    env[harness.DATABASE_URL_ENV] = database_url
    env[harness.REDIS_URL_ENV] = redis_url
    env[harness.FAKE_API_KEY_ENV] = os.environ.get(
        harness.FAKE_API_KEY_ENV,
        harness.DEFAULT_FAKE_API_KEY,
    )
    env[harness.POSTGRES_USER_ENV] = postgres.user
    env[harness.POSTGRES_PASSWORD_ENV] = postgres.password
    harness.ensure_subprocess_pythonpath(env)
    return env


def _spawn_runtime_entry(
    *,
    entry: str,
    env: dict[str, str],
    worker_role: str | None = None,
) -> subprocess.Popen[str]:
    if entry == "coordinator":
        command = [
            sys.executable,
            "-c",
            "from runtime.runners import _entry_coordinator; _entry_coordinator()",
        ]
    elif entry == "api":
        command = [
            sys.executable,
            "-c",
            "from runtime.runners import _entry_api; _entry_api()",
        ]
    elif entry == "worker":
        if worker_role is None:
            raise ValueError("worker_role is required for worker entry")
        command = [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.argv = ['cartoon-demo-worker', '--role', {worker_role!r}]; "
                "from runtime.runners import _entry_worker; _entry_worker()"
            ),
        ]
    else:
        raise ValueError(f"unsupported entry: {entry}")

    return subprocess.Popen(
        command,
        env=env,
        cwd=str(_REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _terminate_process(proc: subprocess.Popen[str], *, label: str) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@contextmanager
def _production_subprocess_stack(
    *,
    config_path: Path,
    database_url: str,
    redis_url: str,
) -> Iterator[str]:
    """Start coordinator, four workers, and API; tear down on exit."""
    env = _build_process_env(
        config_path=config_path,
        database_url=database_url,
        redis_url=redis_url,
    )
    procs: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        procs.append(
            ("coordinator", _spawn_runtime_entry(entry="coordinator", env=env))
        )
        for role in _WORKER_ROLES:
            procs.append(
                (f"worker-{role}", _spawn_runtime_entry(entry="worker", env=env, worker_role=role))
            )
        procs.append(("api", _spawn_runtime_entry(entry="api", env=env)))

        base = harness.http_client_base_url(host="127.0.0.1", port=8000)
        api_proc = procs[-1][1]
        try:
            _wait_http_ok(f"{base}{PATH_HEALTH}", timeout_seconds=60.0)
            _wait_http_ok(f"{base}{PATH_READY}", timeout_seconds=60.0)
        except TimeoutError:
            for label, proc in procs:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
            diagnostics: list[tuple[str, int | None, str, str]] = []
            for label, proc in procs:
                try:
                    stdout, stderr = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate(timeout=5)
                diagnostics.append((label, proc.returncode, stdout, stderr))
            pytest.fail(
                "Production stack failed to become ready "
                f"(diagnostics={diagnostics!r})"
            )

        yield base
    finally:
        for label, proc in reversed(procs):
            _terminate_process(proc, label=label)


def _wait_for_workflow_state(
    *,
    base_url: str,
    workflow_id: str,
    target_state: WorkflowState,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    import httpx

    deadline = time.monotonic() + timeout_seconds
    last_body: dict[str, Any] | None = None
    status_url = f"{base_url}{PATH_WORKFLOW_BY_ID.format(workflow_id=workflow_id)}"

    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(status_url)
                if response.status_code == 200:
                    last_body = response.json()
                    if last_body.get("state") == target_state.value:
                        return last_body
            except httpx.HTTPError as exc:
                last_body = {"poll_error": str(exc)}
            time.sleep(1.0)

    pytest.fail(
        f"workflow {workflow_id} did not reach {target_state.value} within "
        f"{timeout_seconds}s (last={last_body!r})"
    )


@pytest.mark.it_int("INT-006-SUBPROCESS")
def test_int_006_subprocess_e2e_reaches_awaiting_human_approval(
    tmp_path: Path,
    integration_infra: dict[str, str],
    integration_schema: Path,
) -> None:
    """INT-006: real processes + fake provider → AWAITING_HUMAN_APPROVAL (ACD-FR-059)."""
    _assert_public_interface_only()
    _ = integration_schema

    if not _port_free("127.0.0.1", 8000):
        pytest.skip(
            "EXTERNAL_EVIDENCE_REQUIRED: default API port 8000 is busy; "
            "cannot bind cartoon-demo-api for subprocess E2E"
        )

    database_url = integration_infra[harness.DATABASE_URL_ENV]
    redis_url = integration_infra[harness.REDIS_URL_ENV]
    config_path = harness.write_temp_config_yaml(
        tmp_path / "cartoon.subprocess-e2e.yaml",
        database_url=database_url,
        redis_url=redis_url,
    )
    _reset_task_streams(redis_url)

    with _production_subprocess_stack(
        config_path=config_path,
        database_url=database_url,
        redis_url=redis_url,
    ) as base_url:
        import httpx

        with httpx.Client(timeout=10.0) as client:
            created = client.post(
                f"{base_url}{PATH_WORKFLOWS}",
                json={"actor": "integration-subprocess-e2e"},
            )
            assert created.status_code == 201, created.text
            workflow_id = created.json()["workflow_id"]
            assert workflow_id

        terminal = _wait_for_workflow_state(
            base_url=base_url,
            workflow_id=workflow_id,
            target_state=WorkflowState.AWAITING_HUMAN_APPROVAL,
        )
        assert terminal["workflow_id"] == workflow_id
        assert terminal["state"] == WorkflowState.AWAITING_HUMAN_APPROVAL.value
