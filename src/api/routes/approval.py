"""Human approval route handler."""

# GUARDRAIL: Human gate — irreversible approve/reject/regenerate requires explicit human action.

from __future__ import annotations

from ..concurrency import _run_sync
from ..constants import ROUTE_APPROVAL, SPAN_APPROVAL
from ..errors import ApiError
from ..mappers import map_approval_result
from ..protocols import ApiDependencies
from ..telemetry import get_active_telemetry
from ..types import SubmitApprovalApiRequest, SubmitApprovalApiResponse
from ..validation import RequestValidator
from workflow import WorkflowError

from ._helpers import api_error_to_http, unexpected_to_http, workflow_error_to_http


async def handle_submit_approval(
    *,
    deps: ApiDependencies,
    workflow_id: str,
    request: SubmitApprovalApiRequest,
    header_idempotency_key: str | None = None,
) -> SubmitApprovalApiResponse:
    """POST /workflows/{workflow_id}/approval — submit approval action (ACD-API-005)."""
    telemetry = get_active_telemetry()
    validator = RequestValidator()
    wf_id = validator.validate_workflow_id(workflow_id)
    validated = validator.validate_approval_body(
        action=request.action.value,
        actor=request.actor,
        idempotency_key=request.idempotency_key,
        header_idempotency_key=header_idempotency_key,
    )

    span = telemetry.start_route_span(SPAN_APPROVAL, attributes={"workflow_id": wf_id})
    with span:
        try:
            result = await _run_sync(
                lambda: deps.workflow_engine.apply_approval_action(
                    workflow_id=wf_id,
                    action=validated.action,
                    actor=validated.actor,
                    idempotency_key=validated.idempotency_key,
                ),
            )
        except WorkflowError as exc:
            raise workflow_error_to_http(
                exc,
                route_id=ROUTE_APPROVAL,
                workflow_id=wf_id,
            ) from exc
        except ApiError as exc:
            raise api_error_to_http(exc) from exc
        except Exception as exc:
            raise unexpected_to_http(
                exc,
                route_id=ROUTE_APPROVAL,
                workflow_id=wf_id,
            ) from exc

        telemetry.emit_approval_submitted(
            workflow_id=wf_id,
            action=validated.action.value,
        )
        telemetry.emit_request_success(
            route_id=ROUTE_APPROVAL,
            http_method="POST",
            status_code=200,
        )
        return map_approval_result(result)
