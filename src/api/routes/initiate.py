"""Initiate workflow route handler."""

from __future__ import annotations

import hashlib

from workflow import WorkflowError

from ..concurrency import _run_sync
from ..constants import ROUTE_INITIATE, SPAN_INITIATE
from ..errors import ApiError, ApiHttpException
from ..mappers import map_initiate_result, map_to_initiate_request
from ..protocols import ApiDependencies
from ..telemetry import get_active_correlation_context, get_active_telemetry
from ..trace import TraceExtractor
from ..types import InitiateWorkflowApiRequest, InitiateWorkflowApiResponse
from ..validation import RequestValidator

from ._helpers import api_error_to_http, unexpected_to_http, workflow_error_to_http


async def handle_initiate_workflow(
    *,
    deps: ApiDependencies,
    request: InitiateWorkflowApiRequest,
    idempotency_header: str | None = None,
) -> InitiateWorkflowApiResponse:
    """POST /workflows — create workflow and return workflow_id (ACD-API-001)."""
    telemetry = get_active_telemetry()
    validator = RequestValidator()
    trace_extractor = TraceExtractor()

    span = telemetry.start_route_span(SPAN_INITIATE)
    try:
        with span:
            validated = validator.validate_initiate_body(
                workflow_id=request.workflow_id,
                correlation_id=request.correlation_id,
                actor=request.actor,
            )
            idem = validator.validate_idempotency_header(idempotency_header)
            if idem:
                key_prefix = hashlib.sha256(idem.encode()).hexdigest()[:8]
                telemetry._logger.debug(  # noqa: SLF001
                    "initiate_idempotency_key_seen",
                    "Idempotency key observed for initiate request",
                    key_prefix=key_prefix,
                )

            wf_request = map_to_initiate_request(validated)
            try:
                result = await _run_sync(
                    lambda: deps.workflow_engine.initiate_workflow(
                        config=deps.config,
                        request=wf_request,
                    ),
                )
            except WorkflowError as exc:
                raise workflow_error_to_http(exc, route_id=ROUTE_INITIATE) from exc
            except ApiError as exc:
                raise api_error_to_http(exc) from exc
            except Exception as exc:
                raise unexpected_to_http(exc, route_id=ROUTE_INITIATE) from exc

            trace_id = trace_extractor.current_trace_id()
            with get_active_correlation_context().bind(workflow_id=result.workflow_id):
                span.set_attribute("workflow_id", result.workflow_id)
                telemetry.emit_workflow_initiated(workflow_id=result.workflow_id)
                return map_initiate_result(result, trace_id=trace_id)
    except ApiHttpException:
        raise
