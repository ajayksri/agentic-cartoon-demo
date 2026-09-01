"""CLI flag tokens, env names, validation limits, and observability names."""

from __future__ import annotations

import re

CLI_PROG_NAME = "cartoon"
CLI_VERSION = "1.0.0"
USER_AGENT = f"cartoon-cli/{CLI_VERSION}"

ENV_API_URL = "CARTOON_API_URL"
ENV_CONFIG_PATH = "CARTOON_CONFIG_PATH"
ENV_REQUEST_TIMEOUT = "CARTOON_CLI_TIMEOUT"
ENV_DEBUG_TRACEBACK = "CARTOON_CLI_DEBUG"

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0

FLAG_API_URL = "--api-url"
FLAG_CONFIG_PATH = "--config-path"
FLAG_TIMEOUT = "--timeout"
FLAG_INJECT = "--inject"
FLAG_OUTPUT = "--output"

SUBCMD_INITIATE = "initiate"
SUBCMD_STATUS = "status"
SUBCMD_HISTORY = "history"
SUBCMD_OUTPUT = "output"
SUBCMD_TIMELINE = "timeline"
SUBCMD_APPROVE = "approve"

FLAG_WORKFLOW_ID = "--workflow-id"
FLAG_CORRELATION_ID = "--correlation-id"
FLAG_ACTOR = "--actor"
FLAG_ACTION = "--action"

MAX_WORKFLOW_ID_LEN = 128
WORKFLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_CORRELATION_ID_LEN = 128
MAX_ACTOR_LEN = 256

HEADER_TRACEPARENT = "traceparent"
HEADER_TRACESTATE = "tracestate"

SPAN_INITIATE = "cli.initiate"
SPAN_STATUS = "cli.status"
SPAN_HISTORY = "cli.history"
SPAN_OUTPUT = "cli.output"
SPAN_TIMELINE = "cli.timeline"
SPAN_APPROVE = "cli.approve"
SPAN_HTTP_REQUEST = "cli.http.request"

METRIC_COMMANDS_TOTAL = "cli_commands_total"
METRIC_COMMAND_DURATION = "cli_command_duration_seconds"

EXIT_CLASS_SUCCESS = "success"
EXIT_CLASS_ERROR = "error"
EXIT_CLASS_USAGE = "usage"
EXIT_CLASS_CONNECTION = "connection"
