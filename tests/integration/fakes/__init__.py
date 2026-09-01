"""Protocol-conformant integration fakes (INT-003; LLD-RT-001 deferral)."""

from __future__ import annotations

from tests.integration.fakes.asgi_api_client import AsgiApiClient
from tests.integration.fakes.finj_worker import InjectableBoundaryWorker
from tests.integration.fakes.null_logger import NullLogger
from tests.integration.fakes.scenario_workflow import ScenarioWorkflowEngine
from tests.integration.fakes.stack import ScenarioStack, build_scenario_stack
from tests.integration.fakes.trace_pipeline import TracePipelineCapture

__all__ = [
    "AsgiApiClient",
    "InjectableBoundaryWorker",
    "NullLogger",
    "ScenarioStack",
    "ScenarioWorkflowEngine",
    "TracePipelineCapture",
    "build_scenario_stack",
]
