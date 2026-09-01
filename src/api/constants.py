"""Route identifiers, paths, validation limits, and observability names."""

from __future__ import annotations

import re

ROUTE_INITIATE = "initiate"
ROUTE_STATUS = "status"
ROUTE_HISTORY = "history"
ROUTE_OUTPUT = "output"
ROUTE_APPROVAL = "approval"
ROUTE_TIMELINE = "timeline"
ROUTE_HEALTH = "health"
ROUTE_READY = "ready"

PATH_INITIATE = "/workflows"
PATH_STATUS = "/workflows/{workflow_id}"
PATH_HISTORY = "/workflows/{workflow_id}/history"
PATH_OUTPUT = "/workflows/{workflow_id}/output"
PATH_APPROVAL = "/workflows/{workflow_id}/approval"
PATH_TIMELINE = "/workflows/{workflow_id}/timeline"
PATH_HEALTH = "/health"
PATH_READY = "/ready"

PATH_WORKFLOWS = PATH_INITIATE
PATH_WORKFLOW_BY_ID = PATH_STATUS
PATH_WORKFLOW_HISTORY = PATH_HISTORY
PATH_WORKFLOW_OUTPUT = PATH_OUTPUT
PATH_WORKFLOW_APPROVAL = PATH_APPROVAL
PATH_WORKFLOW_TIMELINE = PATH_TIMELINE

METHOD_POST = "POST"
METHOD_GET = "GET"

MAX_WORKFLOW_ID_LEN = 128
WORKFLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_CORRELATION_ID_LEN = 128
MAX_ACTOR_LEN = 256
MAX_IDEMPOTENCY_KEY_LEN = 256

HEADER_TRACEPARENT = "traceparent"
HEADER_TRACESTATE = "tracestate"
HEADER_IDEMPOTENCY_KEY = "idempotency-key"

SPAN_INITIATE = "api.initiate_workflow"
SPAN_STATUS = "api.get_status"
SPAN_HISTORY = "api.get_history"
SPAN_OUTPUT = "api.get_output"
SPAN_APPROVAL = "api.submit_approval"
SPAN_TIMELINE = "api.get_timeline"
SPAN_HEALTH = "api.health"
SPAN_READY = "api.ready"

ROUTE_MODULES: tuple[str, ...] = (
    "api.routes.initiate",
    "api.routes.status",
    "api.routes.history",
    "api.routes.output",
    "api.routes.approval",
    "api.routes.timeline",
    "api.routes.health",
)
