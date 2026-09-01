"""aiohttp HTTP transport for CLI ApiClient."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from observability.protocols import Logger

from .constants import USER_AGENT
from .errors import CliApiError, CliConnectionError, map_to_connection_error

if TYPE_CHECKING:
    import aiohttp


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: dict[str, Any] | None


class HttpTransport:
    """JSON HTTP transport using aiohttp."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        logger: Logger,
        session: object | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._logger = logger
        self._session = session
        self._owns_session = session is None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        import aiohttp

        session = await self._get_session()
        url = f"{self._base_url}{path}"
        request_headers = {"User-Agent": USER_AGENT}
        if headers:
            request_headers.update(headers)
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with session.request(
                method,
                url,
                json=json_body,
                headers=request_headers,
                timeout=timeout,
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    if not text.strip():
                        raise CliApiError("API request failed")
                    try:
                        body = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise CliApiError("API request failed") from exc
                    if not isinstance(body, dict):
                        raise CliApiError("API request failed")
                    return HttpResponse(status=response.status, body=body)
                if not text.strip():
                    return HttpResponse(status=response.status, body=None)
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise CliApiError("API response was malformed") from exc
                if not isinstance(parsed, dict):
                    raise CliApiError("API response was malformed")
                return HttpResponse(status=response.status, body=parsed)
        except CliApiError:
            raise
        except Exception as exc:
            raise map_to_connection_error(exc) from exc

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> object:
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session
