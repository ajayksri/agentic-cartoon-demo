"""Compose API + CLI + scenario engine for INT-003 scenarios A/G."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import ApiDependencies, create_api_router
from cli import (
    CliClientConfig,
    CliDependencies,
    SubcommandRegistry,
    build_default_subcommand_registry,
    create_cli_app,
)
from config.types import ProviderId
from tests.integration.fakes.asgi_api_client import AsgiApiClient
from tests.integration.fakes.null_logger import NullLogger
from tests.integration.fakes.scenario_workflow import ScenarioWorkflowEngine
from tests.integration.test_startup_shutdown import _FailingProbe


@dataclass
class ScenarioStack:
    """Wired composition for scenario A/G integration tests."""

    engine: ScenarioWorkflowEngine
    app: FastAPI
    client: TestClient
    api_client: AsgiApiClient
    cli_app: Any
    config: Any


def build_scenario_stack(config: Any) -> ScenarioStack:
    """Build API router + CLI against injectable ScenarioWorkflowEngine."""
    for agent in config.agents.values():
        assert agent.provider == ProviderId.FAKE, (
            f"integration scenarios require fake provider, got {agent.provider}"
        )

    engine = ScenarioWorkflowEngine()
    deps = ApiDependencies(
        config=config,
        workflow_engine=engine,  # type: ignore[arg-type]
        readiness_probes=(_FailingProbe("postgres"), _FailingProbe("redis")),
        service_name="cartoon-demo-api",
    )
    router = create_api_router(deps=deps)
    app = FastAPI()
    app.include_router(router)  # type: ignore[arg-type]
    client = TestClient(app)
    api_client = AsgiApiClient(client)

    logger = NullLogger()
    seed = CliDependencies(
        client_config=CliClientConfig(api_base_url="http://testserver"),
        registry=SubcommandRegistry(specs={}, handlers={}),
        logger=logger,
    )
    registry = build_default_subcommand_registry(deps=seed)
    cli_deps = CliDependencies(
        client_config=CliClientConfig(api_base_url="http://testserver"),
        registry=registry,
        logger=logger,
    )
    cli_app = create_cli_app(deps=cli_deps, api_client=api_client)
    return ScenarioStack(
        engine=engine,
        app=app,
        client=client,
        api_client=api_client,
        cli_app=cli_app,
        config=config,
    )
