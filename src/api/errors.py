"""Public API error types and workflow error mapping."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from workflow import (
    InvalidApprovalActionError,
    InvalidTransitionError,
    WorkflowConflictError,
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowTerminalError,
)

from .telemetry import get_active_telemetry
from .types import ApiErrorEnvelope

_WORKFLOW_ERROR_HTTP_STATUS: dict[type[WorkflowError], int] = {
    WorkflowNotFoundError: 404,
    InvalidApprovalActionError: 409,
    WorkflowTerminalError: 409,
    WorkflowConflictError: 409,
    InvalidTransitionError: 409,
}


class ApiError(Exception):
    """Base API-layer error carrying HTTP mapping metadata."""

    error_class: str = "API_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        retryable: bool | None = None,
        workflow_id: str | None = None,
        details: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.workflow_id = workflow_id
        self.details = details

    def to_envelope(self) -> ApiErrorEnvelope:
        return ApiErrorEnvelope(
            error_class=self.error_class,
            message=str(self),
            retryable=self.retryable,
            workflow_id=self.workflow_id,
            details=self.details,
        )


class ApiValidationError(ApiError):
    """Request body or path parameter failed validation."""

    error_class = "API_VALIDATION"
    http_status = 400


class ApiNotFoundError(ApiError):
    """Requested workflow or resource does not exist."""

    error_class = "WF_NOT_FOUND"
    http_status = 404


class ApiConflictError(ApiError):
    """Optimistic conflict, invalid approval, or terminal workflow mutation."""

    error_class = "WF_CONFLICT"
    http_status = 409


class ApiInternalError(ApiError):
    """Unexpected internal failure."""

    error_class = "API_INTERNAL"
    http_status = 500


def workflow_error_http_status(error: WorkflowError) -> int:
    """Resolve HTTP status for a workflow exception (LLD-API-001)."""
    return _WORKFLOW_ERROR_HTTP_STATUS.get(type(error), 500)


def map_workflow_error(error: WorkflowError) -> ApiErrorEnvelope:
    """Map a workflow domain error to the REST error envelope."""
    workflow_id = getattr(error, "workflow_id", None)
    if isinstance(error, WorkflowNotFoundError):
        return ApiNotFoundError(
            str(error),
            workflow_id=workflow_id,
            retryable=False,
        ).to_envelope()
    if isinstance(error, WorkflowConflictError):
        return ApiConflictError(
            str(error),
            workflow_id=workflow_id,
            retryable=False,
        ).to_envelope()
    if isinstance(error, (InvalidApprovalActionError, InvalidTransitionError, WorkflowTerminalError)):
        error_class = error.code
        return ApiErrorEnvelope(
            error_class=error_class,
            message=str(error),
            retryable=False,
            workflow_id=workflow_id,
        )
    return ApiInternalError(str(error), workflow_id=workflow_id).to_envelope()


def map_unexpected_error(
    exc: Exception,
    *,
    route_id: str,
    workflow_id: str | None = None,
) -> ApiHttpException:
    """Log internal error and return sanitized ApiInternalError envelope."""
    telemetry = get_active_telemetry()
    telemetry.emit_internal_error(route_id=route_id)
    envelope = ApiInternalError(
        "An internal error occurred",
        workflow_id=workflow_id,
    ).to_envelope()
    return ApiHttpException(http_status=500, envelope=envelope)


@dataclass(frozen=True, slots=True)
class ApiHttpException(Exception):
    """Framework-neutral carrier raised by handlers; converted by exception handler."""

    http_status: int
    envelope: ApiErrorEnvelope
    response_headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "response_headers", dict(self.response_headers))
