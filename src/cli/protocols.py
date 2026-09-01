"""Public CLI application and API client protocols."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from api.types import (
    HealthResponse,
    InitiateWorkflowApiRequest,
    InitiateWorkflowApiResponse,
    SubmitApprovalApiRequest,
    SubmitApprovalApiResponse,
    WorkflowHistoryResponse,
    WorkflowOutputResponse,
    WorkflowStatusResponse,
    WorkflowTimelineResponse,
)
from observability.protocols import Logger, Tracer

from .types import CliClientConfig, SubcommandRegistry

if TYPE_CHECKING:
    from observability.types import TraceContext


class ApiClient(Protocol):
    """HTTP client for the api REST surface."""

    @property
    def base_url(self) -> str:
        """API base URL including scheme and host."""
        ...

    async def initiate_workflow(
        self,
        request: InitiateWorkflowApiRequest,
        *,
        trace_context: TraceContext | None = None,
    ) -> InitiateWorkflowApiResponse:
        """POST /workflows — initiate a new workflow run."""
        ...

    async def get_workflow_status(self, workflow_id: str) -> WorkflowStatusResponse:
        """GET /workflows/{workflow_id} — query current workflow state."""
        ...

    async def get_workflow_history(self, workflow_id: str) -> WorkflowHistoryResponse:
        """GET /workflows/{workflow_id}/history — query transition history."""
        ...

    async def get_workflow_output(self, workflow_id: str) -> WorkflowOutputResponse:
        """GET /workflows/{workflow_id}/output — retrieve output package."""
        ...

    async def get_workflow_timeline(self, workflow_id: str) -> WorkflowTimelineResponse:
        """GET /workflows/{workflow_id}/timeline — human-readable timeline."""
        ...

    async def submit_approval(
        self,
        workflow_id: str,
        request: SubmitApprovalApiRequest,
    ) -> SubmitApprovalApiResponse:
        """POST /workflows/{workflow_id}/approval — submit human approval action."""
        ...

    async def health_check(self) -> HealthResponse:
        """GET /health — API liveness probe."""
        ...


@dataclass(frozen=True, slots=True)
class CliDependencies:
    """Dependencies supplied to CliApp and subcommand registry."""

    client_config: CliClientConfig
    registry: SubcommandRegistry
    logger: Logger
    tracer: Tracer | None = None


class CliApp(Protocol):
    """CLI application entry — parse argv, dispatch subcommand, return exit code."""

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Parse argv, execute subcommand, map result to process exit code."""
        ...


def create_api_client(*, config: CliClientConfig, logger: Logger) -> ApiClient:
    """Default ApiClient factory (CG-CLI-009)."""
    from .client import create_api_client as _create_api_client

    return _create_api_client(config=config, logger=logger)


def create_cli_app(
    *,
    deps: CliDependencies,
    api_client: ApiClient | None = None,
    telemetry: object | None = None,
) -> CliApp:
    """Default CliApp factory.

    Optional ``api_client`` injects a test double for contract tests (LLD §14).
    """
    from .app import create_cli_app as _create_cli_app

    return _create_cli_app(deps=deps, api_client=api_client, telemetry=telemetry)


def run_cli(argv: Sequence[str] | None = None, *, deps: CliDependencies) -> int:
    """Primary public entry point for CLI process main()."""
    from .app import run_cli as _run_cli

    return _run_cli(argv, deps=deps)


def build_default_subcommand_registry(
    *,
    deps: CliDependencies,
    telemetry: object | None = None,
) -> SubcommandRegistry:
    """Construct registry with handlers for all V1 subcommands."""
    from .registry import build_default_subcommand_registry as _build

    return _build(deps=deps, telemetry=telemetry)  # type: ignore[arg-type]
