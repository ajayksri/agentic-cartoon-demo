"""Unit tests for CLI error mapping."""

from __future__ import annotations

from api.types import ApiErrorEnvelope
from cli.errors import CliApiError, CliConnectionError, CliUsageError, map_api_error_envelope, map_to_connection_error
from cli.types import CliExitCode


def test_map_api_error_envelope_known_class() -> None:
    envelope = ApiErrorEnvelope(
        error_class="WF_NOT_FOUND",
        message="missing",
        workflow_id="wf-1",
    )
    error = map_api_error_envelope(envelope, http_status=404, workflow_id="wf-1")
    assert isinstance(error, CliApiError)
    assert "wf-1" in str(error)
    assert error.exit_code == CliExitCode.ERROR


def test_map_api_error_envelope_unknown_class_uses_message() -> None:
    envelope = ApiErrorEnvelope(error_class="UNKNOWN", message="bounded message")
    error = map_api_error_envelope(envelope, http_status=500)
    assert str(error) == "bounded message"


def test_map_to_connection_error_timeout() -> None:
    error = map_to_connection_error(TimeoutError("timed out"))
    assert isinstance(error, CliConnectionError)
    assert error.exit_code == CliExitCode.CONNECTION


def test_cli_error_codes() -> None:
    assert CliUsageError("x").code == "CLI_USAGE"
    assert CliApiError("x").exit_code == CliExitCode.ERROR
