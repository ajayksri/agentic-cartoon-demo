"""Default subcommand registry."""

from __future__ import annotations

from .handlers.approve import ApproveHandler
from .handlers.history import HistoryHandler
from .handlers.initiate import InitiateHandler
from .handlers.output import OutputHandler
from .handlers.status import StatusHandler
from .handlers.timeline import TimelineHandler
from .protocols import CliDependencies
from .render import OutputRenderer
from .telemetry import CliTelemetry
from .types import SubcommandId, SubcommandRegistry, SubcommandSpec
from .validation import InputValidator


def build_default_subcommand_registry(
    *,
    deps: CliDependencies,
    telemetry: CliTelemetry | None = None,
) -> SubcommandRegistry:
    """Construct registry with handlers for all V1 subcommands."""
    validator = InputValidator()
    renderer = OutputRenderer()
    resolved_telemetry = telemetry or CliTelemetry(
        logger=deps.logger,
        tracer=deps.tracer,
    )

    specs = {
        SubcommandId.INITIATE: SubcommandSpec(
            id=SubcommandId.INITIATE,
            name="initiate",
            description="Initiate a new workflow run",
            requires_workflow_id=False,
        ),
        SubcommandId.STATUS: SubcommandSpec(
            id=SubcommandId.STATUS,
            name="status",
            description="Query workflow status",
            requires_workflow_id=True,
        ),
        SubcommandId.HISTORY: SubcommandSpec(
            id=SubcommandId.HISTORY,
            name="history",
            description="Query workflow transition history",
            requires_workflow_id=True,
        ),
        SubcommandId.OUTPUT: SubcommandSpec(
            id=SubcommandId.OUTPUT,
            name="output",
            description="Retrieve workflow output package",
            requires_workflow_id=True,
        ),
        SubcommandId.TIMELINE: SubcommandSpec(
            id=SubcommandId.TIMELINE,
            name="timeline",
            description="Display workflow timeline",
            requires_workflow_id=True,
        ),
        SubcommandId.APPROVE: SubcommandSpec(
            id=SubcommandId.APPROVE,
            name="approve",
            description="Submit human approval action",
            requires_workflow_id=True,
        ),
    }

    handlers = {
        SubcommandId.INITIATE: InitiateHandler(
            subcommand_id=SubcommandId.INITIATE,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
        SubcommandId.STATUS: StatusHandler(
            subcommand_id=SubcommandId.STATUS,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
        SubcommandId.HISTORY: HistoryHandler(
            subcommand_id=SubcommandId.HISTORY,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
        SubcommandId.OUTPUT: OutputHandler(
            subcommand_id=SubcommandId.OUTPUT,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
        SubcommandId.TIMELINE: TimelineHandler(
            subcommand_id=SubcommandId.TIMELINE,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
        SubcommandId.APPROVE: ApproveHandler(
            subcommand_id=SubcommandId.APPROVE,
            validator=validator,
            renderer=renderer,
            telemetry=resolved_telemetry,
        ),
    }

    return SubcommandRegistry(specs=specs, handlers=handlers)
