"""Shared workflow route handler utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from workflow import WorkflowError

from ..constants import ROUTE_STATUS
from ..errors import (
    ApiError,
    ApiHttpException,
    map_unexpected_error,
    map_workflow_error,
    workflow_error_http_status,
)
from ..telemetry import get_active_telemetry

if TYPE_CHECKING:
    from ..protocols import ApiDependencies

T = TypeVar("T")


async def run_workflow_handler(
    *,
    route_id: str,
    span_name: str,
    workflow_id: str | None,
    operation: str,
) -> None:
    del span_name, operation
    del route_id, workflow_id


def workflow_error_to_http(
    error: WorkflowError,
    *,
    route_id: str,
    workflow_id: str | None = None,
) -> ApiHttpException:
    envelope = map_workflow_error(error)
    telemetry = get_active_telemetry()
    telemetry.emit_workflow_error(
        workflow_id=getattr(error, "workflow_id", workflow_id),
        error_class=envelope.error_class,
        route_id=route_id,
    )
    return ApiHttpException(
        http_status=workflow_error_http_status(error),
        envelope=envelope,
    )


def api_error_to_http(error: ApiError) -> ApiHttpException:
    return ApiHttpException(http_status=error.http_status, envelope=error.to_envelope())


def unexpected_to_http(
    exc: Exception,
    *,
    route_id: str,
    workflow_id: str | None = None,
) -> ApiHttpException:
    return map_unexpected_error(exc, route_id=route_id, workflow_id=workflow_id)
