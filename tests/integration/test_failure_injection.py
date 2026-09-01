"""IT-FINJ-004 / IT-FINJ-005 — failure injection surface + CLI enablement.

IT-FINJ-004 from INT-002; IT-FINJ-005 added in INT-004.
"""

from __future__ import annotations

from typing import Any

import pytest

from api import (
    ApiDependencies,
    create_api_router,
)
from cli import CliConfigOverride, merge_cli_config_override, parse_failure_injection_flags
from failure_injection import InjectionId
from tests.integration.fakes.finj_worker import (
    InjectableBoundaryWorker,
    recording_only,
)
from tests.integration.test_startup_shutdown import (
    _FailingProbe,
    _StubWorkflowEngine,
    _make_test_client,
)

pytestmark = [pytest.mark.integration]


_INJECTION_PATH_TOKENS = (
    "inject",
    "injection",
    "failure_injection",
    "failure-injection",
    "finj",
)


def _registered_routes(router: object) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in getattr(router, "routes", ()):
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append((method, path))
    return routes


@pytest.mark.it_int("IT-FINJ-004")
def test_it_finj_004_no_api_route_accepts_injection_controls(
    integration_app_config: Any,
) -> None:
    """IT-FINJ-004: no public API route accepts failure-injection controls (ACD-SEC-007)."""
    deps = ApiDependencies(
        config=integration_app_config,
        workflow_engine=_StubWorkflowEngine(),  # type: ignore[arg-type]
        readiness_probes=(_FailingProbe("postgres"),),
        service_name="cartoon-demo-api",
    )
    router = create_api_router(deps=deps)
    routes = _registered_routes(router)

    assert routes, "expected API routes to be registered"
    offending = [
        (method, path)
        for method, path in routes
        if any(token in path.lower() for token in _INJECTION_PATH_TOKENS)
    ]
    assert offending == [], f"failure-injection REST surface must not exist: {offending}"

    client = _make_test_client(router)
    for path in (
        "/inject",
        "/failure-injection",
        "/failure_injection",
        "/finj",
        "/admin/inject",
        "/v1/failure-injection",
    ):
        for method in ("GET", "POST", "PUT", "DELETE"):
            response = client.request(method, path)
            assert response.status_code == 404, (
                f"{method} {path} must not expose injection controls "
                f"(got {response.status_code})"
            )


@pytest.mark.it_int("IT-FINJ-005")
def test_it_finj_005_cli_inject_merges_and_worker_observes_hook(
    integration_app_config: Any,
) -> None:
    """IT-FINJ-005: CLI --inject merges config; worker observes active hook (ACD-CLI-003)."""
    override = parse_failure_injection_flags(
        ["--inject", InjectionId.FINJ_WKR_POST_AGENT.value]
    )
    assert override is not None
    assert override.enabled is True
    assert InjectionId.FINJ_WKR_POST_AGENT.value in override.active_injections

    merged = merge_cli_config_override(
        integration_app_config,
        CliConfigOverride(failure_injection=override),
    )
    assert merged.failure_injection.enabled is True
    assert merged.is_injection_active(InjectionId.FINJ_WKR_POST_AGENT)

    hook = recording_only()
    worker = InjectableBoundaryWorker.create(
        merged,
        hook_specs={InjectionId.FINJ_WKR_POST_AGENT: hook},
    )
    assert InjectionId.FINJ_WKR_POST_AGENT.value in worker.observed_active_injections

    invoked = worker.registry.invoke_if_active(InjectionId.FINJ_WKR_POST_AGENT)
    assert invoked is True
    assert len(hook.calls) == 1
