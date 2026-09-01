"""FastAPI router factory and route binding wrappers."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .constants import (
    HEADER_IDEMPOTENCY_KEY,
    PATH_HEALTH,
    PATH_READY,
    PATH_WORKFLOW_APPROVAL,
    PATH_WORKFLOW_BY_ID,
    PATH_WORKFLOW_HISTORY,
    PATH_WORKFLOW_OUTPUT,
    PATH_WORKFLOW_TIMELINE,
    PATH_WORKFLOWS,
    ROUTE_APPROVAL,
    ROUTE_HEALTH,
    ROUTE_HISTORY,
    ROUTE_INITIATE,
    ROUTE_OUTPUT,
    ROUTE_READY,
    ROUTE_STATUS,
    ROUTE_TIMELINE,
)
from .errors import ApiError, ApiHttpException
from .protocols import ApiDependencies, MutatingRouteContext
from .routes.approval import handle_submit_approval
from .routes.health import handle_health, handle_readiness
from .routes.history import handle_get_workflow_history
from .routes.initiate import handle_initiate_workflow
from .routes.output import handle_get_workflow_output
from .routes.status import handle_get_workflow_status
from .routes.timeline import handle_get_workflow_timeline
from .serialization import dataclass_to_json_dict, envelope_json
from .telemetry import get_active_telemetry
from .trace import TraceExtractor
from .types import InitiateWorkflowApiRequest, ReadinessStatus, SubmitApprovalApiRequest
from .validation import RequestValidator

T = TypeVar("T")


def _header_lookup(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


class DefaultApiRouterFactory:
    """Creates a FastAPI APIRouter with all API routes registered."""

    def __init__(
        self,
        *,
        mutating_context: MutatingRouteContext | None = None,
    ) -> None:
        self._mutating_context = mutating_context

    def create_router(self, *, deps: ApiDependencies) -> APIRouter:
        router = APIRouter()
        telemetry = get_active_telemetry()
        validator = RequestValidator()
        trace_extractor = TraceExtractor()
        mutating = self._mutating_context

        initiate_handler = self._wrap_initiate(deps, telemetry, validator, trace_extractor)
        approval_handler = self._wrap_approval(deps, telemetry, validator, trace_extractor)

        router.add_api_route(
            PATH_WORKFLOWS,
            mutating.wrap_mutating(initiate_handler) if mutating else initiate_handler,
            methods=["POST"],
            status_code=201,
        )
        router.add_api_route(
            PATH_WORKFLOW_BY_ID,
            self._wrap_status(deps, telemetry, validator, trace_extractor),
            methods=["GET"],
        )
        router.add_api_route(
            PATH_WORKFLOW_HISTORY,
            self._wrap_history(deps, telemetry, validator, trace_extractor),
            methods=["GET"],
        )
        router.add_api_route(
            PATH_WORKFLOW_OUTPUT,
            self._wrap_output(deps, telemetry, validator, trace_extractor),
            methods=["GET"],
        )
        router.add_api_route(
            PATH_WORKFLOW_APPROVAL,
            mutating.wrap_mutating(approval_handler) if mutating else approval_handler,
            methods=["POST"],
        )
        router.add_api_route(
            PATH_WORKFLOW_TIMELINE,
            self._wrap_timeline(deps, telemetry, validator, trace_extractor),
            methods=["GET"],
        )
        router.add_api_route(
            PATH_HEALTH,
            self._wrap_health(deps, telemetry, trace_extractor),
            methods=["GET"],
        )
        router.add_api_route(
            PATH_READY,
            self._wrap_readiness(deps, telemetry, trace_extractor),
            methods=["GET"],
        )

        return router

    def _wrap_initiate(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_INITIATE,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _initiate_call(deps, validator, request),
                success_status=201,
            )

        return _handler

    def _wrap_status(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(workflow_id: str, request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_STATUS,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _status_call(deps, validator, workflow_id),
                success_status=200,
            )

        return _handler

    def _wrap_history(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(workflow_id: str, request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_HISTORY,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _history_call(deps, validator, workflow_id),
                success_status=200,
            )

        return _handler

    def _wrap_output(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(workflow_id: str, request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_OUTPUT,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _output_call(deps, validator, workflow_id),
                success_status=200,
            )

        return _handler

    def _wrap_approval(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(workflow_id: str, request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_APPROVAL,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _approval_call(deps, validator, workflow_id, request),
                success_status=200,
            )

        return _handler

    def _wrap_timeline(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        validator: RequestValidator,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(workflow_id: str, request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_TIMELINE,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: _timeline_call(deps, validator, workflow_id),
                success_status=200,
            )

        return _handler

    def _wrap_health(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(request: Request) -> JSONResponse:
            return await _route_wrapper(
                request=request,
                route_id=ROUTE_HEALTH,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=lambda: handle_health(deps=deps),
                success_status=200,
            )

        return _handler

    def _wrap_readiness(
        self,
        deps: ApiDependencies,
        telemetry: Any,
        trace_extractor: TraceExtractor,
    ) -> Callable[..., Awaitable[JSONResponse]]:
        async def _handler(request: Request) -> JSONResponse:
            async def _call() -> tuple[object, int]:
                response = await handle_readiness(deps=deps)
                status_code = 200 if response.status == ReadinessStatus.READY else 503
                return response, status_code

            return await _route_wrapper(
                request=request,
                route_id=ROUTE_READY,
                telemetry=telemetry,
                trace_extractor=trace_extractor,
                handler_call=_call,
                success_status=200,
                dynamic_status=True,
            )

        return _handler


async def _initiate_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    request: Request,
) -> object:
    body = await _json_body(request)
    validated = validator.validate_initiate_body(
        workflow_id=body.get("workflow_id"),
        correlation_id=body.get("correlation_id"),
        actor=body.get("actor"),
    )
    idempotency_header = _header_lookup(request.headers, HEADER_IDEMPOTENCY_KEY)
    return await handle_initiate_workflow(
        deps=deps,
        request=validated,
        idempotency_header=idempotency_header,
    )


async def _status_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    workflow_id: str,
) -> object:
    wf_id = validator.validate_workflow_id(workflow_id)
    return await handle_get_workflow_status(deps=deps, workflow_id=wf_id)


async def _history_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    workflow_id: str,
) -> object:
    wf_id = validator.validate_workflow_id(workflow_id)
    return await handle_get_workflow_history(deps=deps, workflow_id=wf_id)


async def _output_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    workflow_id: str,
) -> object:
    wf_id = validator.validate_workflow_id(workflow_id)
    return await handle_get_workflow_output(deps=deps, workflow_id=wf_id)


async def _approval_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    workflow_id: str,
    request: Request,
) -> object:
    body = await _json_body(request)
    header_idempotency = _header_lookup(request.headers, HEADER_IDEMPOTENCY_KEY)
    validated = validator.validate_approval_body(
        action=str(body.get("action", "")),
        actor=body.get("actor"),
        idempotency_key=body.get("idempotency_key"),
        header_idempotency_key=header_idempotency,
    )
    wf_id = validator.validate_workflow_id(workflow_id)
    return await handle_submit_approval(
        deps=deps,
        workflow_id=wf_id,
        request=validated,
        header_idempotency_key=header_idempotency,
    )


async def _timeline_call(
    deps: ApiDependencies,
    validator: RequestValidator,
    workflow_id: str,
) -> object:
    wf_id = validator.validate_workflow_id(workflow_id)
    return await handle_get_workflow_timeline(deps=deps, workflow_id=wf_id)


async def _json_body(request: Request) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        from .errors import ApiValidationError

        raise ApiValidationError("request body must be a JSON object")
    return body


async def _route_wrapper(
    *,
    request: Request,
    route_id: str,
    telemetry: Any,
    trace_extractor: TraceExtractor,
    handler_call: Callable[[], Awaitable[object | tuple[object, int]]],
    success_status: int,
    dynamic_status: bool = False,
) -> JSONResponse:
    started = time.perf_counter()
    status_code = success_status
    with trace_extractor.request_scope(dict(request.headers)):
        try:
            result = await handler_call()
            if isinstance(result, tuple):
                payload, status_code = result
            else:
                payload = result
            carrier: dict[str, str] = {}
            trace_extractor.inject_response_headers(carrier)
            telemetry.emit_request_success(
                route_id=route_id,
                http_method=request.method,
                status_code=status_code,
            )
            return JSONResponse(
                content=dataclass_to_json_dict(payload),
                status_code=status_code,
                headers=carrier,
            )
        except ApiHttpException as exc:
            carrier = dict(exc.response_headers)
            trace_extractor.inject_response_headers(carrier)
            status_code = exc.http_status
            return JSONResponse(
                content=envelope_json(exc.envelope),
                status_code=exc.http_status,
                headers=carrier,
            )
        except ApiError as exc:
            telemetry.emit_validation_failed(route_id=route_id)
            carrier: dict[str, str] = {}
            trace_extractor.inject_response_headers(carrier)
            status_code = exc.http_status
            return JSONResponse(
                content=envelope_json(exc.to_envelope()),
                status_code=exc.http_status,
                headers=carrier,
            )
        finally:
            telemetry.record_request_metric(
                route_id=route_id,
                status_code=status_code,
                duration_seconds=time.perf_counter() - started,
            )


async def _api_exception_handler(_request: Request, exc: ApiHttpException) -> JSONResponse:
    return JSONResponse(
        content=envelope_json(exc.envelope),
        status_code=exc.http_status,
        headers=dict(exc.response_headers),
    )


def create_api_router(
    *,
    deps: ApiDependencies,
    mutating_context: MutatingRouteContext | None = None,
) -> APIRouter:
    """Wires DefaultApiRouterFactory with injected deps and exception handlers."""
    return DefaultApiRouterFactory(mutating_context=mutating_context).create_router(deps=deps)
