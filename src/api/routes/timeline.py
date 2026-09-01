"""Workflow timeline route handler."""

from __future__ import annotations

from ..concurrency import _run_sync
from ..constants import ROUTE_TIMELINE, SPAN_TIMELINE
from ..errors import ApiError
from ..mappers import map_workflow_timeline
from ..protocols import ApiDependencies
from ..telemetry import get_active_telemetry
from ..types import WorkflowTimelineResponse
from ..validation import RequestValidator
from workflow import WorkflowError

from ._helpers import api_error_to_http, unexpected_to_http, workflow_error_to_http


async def handle_get_workflow_timeline(
    *,
    deps: ApiDependencies,
    workflow_id: str,
) -> WorkflowTimelineResponse:
    """GET /workflows/{workflow_id}/timeline — human-readable event timeline (ACD-API-007)."""
    telemetry = get_active_telemetry()
    validator = RequestValidator()
    wf_id = validator.validate_workflow_id(workflow_id)

    span = telemetry.start_route_span(SPAN_TIMELINE, attributes={"workflow_id": wf_id})
    with span:
        try:
            timeline = await _run_sync(
                lambda: deps.workflow_engine.get_workflow_timeline(wf_id),
            )
        except WorkflowError as exc:
            raise workflow_error_to_http(
                exc,
                route_id=ROUTE_TIMELINE,
                workflow_id=wf_id,
            ) from exc
        except ApiError as exc:
            raise api_error_to_http(exc) from exc
        except Exception as exc:
            raise unexpected_to_http(
                exc,
                route_id=ROUTE_TIMELINE,
                workflow_id=wf_id,
            ) from exc

        telemetry.emit_request_success(
            route_id=ROUTE_TIMELINE,
            http_method="GET",
            status_code=200,
        )
        return map_workflow_timeline(timeline)
