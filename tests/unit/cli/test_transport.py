"""Unit tests for HttpTransport."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli.constants import USER_AGENT
from cli.errors import CliApiError, CliConnectionError
from cli.fakes.logger import RecordingLogger
from cli.transport import HttpTransport


def _run(coro):
    return asyncio.run(coro)


def _mock_response(*, status: int, text: str) -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _transport(session: object | None = None) -> HttpTransport:
    return HttpTransport(
        base_url="http://api.test",
        timeout_seconds=5.0,
        logger=RecordingLogger(),
        session=session,
    )


def test_request_returns_parsed_json_on_2xx() -> None:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(status=200, text='{"ok": true}'))
    transport = _transport(session=session)

    result = _run(transport.request("GET", "/health"))

    assert result.status == 200
    assert result.body == {"ok": True}
    call_kwargs = session.request.call_args.kwargs
    assert call_kwargs["headers"]["User-Agent"] == USER_AGENT


def test_request_returns_error_envelope_on_4xx() -> None:
    session = MagicMock()
    session.request = MagicMock(
        return_value=_mock_response(
            status=404,
            text='{"error_class":"WF_NOT_FOUND","message":"missing","retryable":false}',
        )
    )
    transport = _transport(session=session)

    result = _run(transport.request("GET", "/workflows/wf-1"))

    assert result.status == 404
    assert result.body is not None
    assert result.body["error_class"] == "WF_NOT_FOUND"


def test_request_raises_cli_api_error_on_empty_4xx_body() -> None:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(status=500, text=""))
    transport = _transport(session=session)

    with pytest.raises(CliApiError, match="API request failed"):
        _run(transport.request("GET", "/workflows/wf-1"))


def test_request_raises_cli_api_error_on_malformed_2xx_json() -> None:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(status=200, text="not-json"))
    transport = _transport(session=session)

    with pytest.raises(CliApiError, match="malformed"):
        _run(transport.request("GET", "/health"))


def test_request_maps_connection_failure_to_cli_connection_error() -> None:
    session = MagicMock()
    session.request = MagicMock(side_effect=ConnectionError("refused"))
    transport = _transport(session=session)

    with pytest.raises(CliConnectionError):
        _run(transport.request("GET", "/health"))


def test_request_maps_timeout_to_cli_connection_error() -> None:
    session = MagicMock()
    session.request = MagicMock(side_effect=TimeoutError())
    transport = _transport(session=session)

    with pytest.raises(CliConnectionError):
        _run(transport.request("GET", "/health"))


def test_close_disposes_owned_session() -> None:
    mock_session = AsyncMock()

    async def _run_close() -> None:
        import aiohttp

        original = aiohttp.ClientSession
        aiohttp.ClientSession = MagicMock(return_value=mock_session)  # type: ignore[misc,assignment]
        try:
            transport = _transport()
            await transport._get_session()
            await transport.close()
        finally:
            aiohttp.ClientSession = original

    _run(_run_close())

    mock_session.close.assert_awaited_once()
