"""Public CLI error types and API error mapping."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from api.types import ApiErrorEnvelope

from .types import CliExitCode

if TYPE_CHECKING:
    import aiohttp

_API_ERROR_MESSAGES: dict[str, str] = {
    "WF_NOT_FOUND": "Workflow '{workflow_id}' was not found.",
    "WF_INVALID_APPROVAL": "Approval action is not valid for workflow '{workflow_id}'.",
    "WF_TERMINAL": "Workflow '{workflow_id}' is in a terminal state.",
    "WF_CONFLICT": "Workflow '{workflow_id}' has a concurrent modification conflict.",
    "WF_INVALID_TRANSITION": "Invalid state transition for workflow '{workflow_id}'.",
    "API_VALIDATION": "Request validation failed.",
    "API_INTERNAL": "An internal server error occurred.",
}


def _connection_error_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [
        asyncio.TimeoutError,
        TimeoutError,
        OSError,
        ConnectionError,
        json.JSONDecodeError,
    ]
    try:
        import aiohttp

        types.insert(0, aiohttp.ClientError)
    except ImportError:
        pass
    return tuple(types)


_CONNECTION_ERROR_TYPES: tuple[type[BaseException], ...] | None = None


def _get_connection_error_types() -> tuple[type[BaseException], ...]:
    global _CONNECTION_ERROR_TYPES
    if _CONNECTION_ERROR_TYPES is None:
        _CONNECTION_ERROR_TYPES = _connection_error_types()
    return _CONNECTION_ERROR_TYPES


class CliError(Exception):
    """Base CLI error with stable code and exit code mapping."""

    code: str = "CLI_ERROR"
    exit_code: CliExitCode = CliExitCode.ERROR

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str | None = None,
        api_error_class: str | None = None,
    ) -> None:
        super().__init__(message)
        self.workflow_id = workflow_id
        self.api_error_class = api_error_class


class CliUsageError(CliError):
    """Invalid flags, missing required args, or unknown injection id."""

    code = "CLI_USAGE"
    exit_code = CliExitCode.USAGE


class CliApiError(CliError):
    """API returned an ApiErrorEnvelope."""

    code = "CLI_API"
    exit_code = CliExitCode.ERROR


class CliConnectionError(CliError):
    """HTTP transport failure or timeout."""

    code = "CLI_CONNECTION"
    exit_code = CliExitCode.CONNECTION


class CliConfigError(CliError):
    """Config load or override merge failure."""

    code = "CLI_CONFIG"
    exit_code = CliExitCode.USAGE


def map_api_error_envelope(
    envelope: ApiErrorEnvelope,
    *,
    http_status: int,
    workflow_id: str | None = None,
) -> CliApiError:
    """Map API JSON error body to CliApiError."""
    _ = http_status
    template = _API_ERROR_MESSAGES.get(envelope.error_class, envelope.message)
    resolved_workflow_id = workflow_id or envelope.workflow_id or "unknown"
    try:
        message = template.format(workflow_id=resolved_workflow_id)
    except (KeyError, IndexError):
        message = envelope.message
    return CliApiError(
        message,
        workflow_id=envelope.workflow_id or workflow_id,
        api_error_class=envelope.error_class,
    )


def map_to_connection_error(exc: BaseException) -> CliConnectionError:
    """Map transport and unexpected exceptions to CliConnectionError."""
    if isinstance(exc, CliConnectionError):
        return exc
    if isinstance(exc, _get_connection_error_types()):
        return CliConnectionError(str(exc))
    return CliConnectionError("Unexpected CLI error")
