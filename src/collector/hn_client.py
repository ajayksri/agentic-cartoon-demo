"""Hacker News HTTP client protocol, fetchers, decoder, and error classifier."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import httpx

from collector.constants import (
    HN_BASE_URL,
    HTTP_CONNECT_TIMEOUT_SECONDS,
    HTTP_TOTAL_TIMEOUT_SECONDS,
    ITEM_PATH_TEMPLATE,
    MAX_CONCURRENT_ITEM_FETCHES,
    TOP_STORIES_PATH,
)
from collector.errors import (
    CollectorError,
    CollectorFetchError,
    CollectorResponseError,
    CollectorTimeoutError,
)
from collector.hn_parser import RawObservation
from collector.messages import collector_error_message


@dataclass(frozen=True, slots=True)
class FeedFetchResult:
    story_ids: list[int]


@dataclass(frozen=True, slots=True)
class ItemFetchResult:
    source_id: str
    status_code: int | None
    body: bytes | None
    error_kind: Literal["none", "timeout", "connection", "http"] = "none"


class HackerNewsClient(Protocol):
    def fetch_top_story_ids(self) -> FeedFetchResult:
        """Fatal on unrecoverable feed failure — raises CollectorError subclass."""
        ...

    def fetch_items(self, story_ids: Sequence[int]) -> list[ItemFetchResult]:
        """Bounded concurrent fetch; per-item failures returned in result list."""
        ...


class ResponseDecoder:
    def decode_feed(self, body: bytes) -> list[int]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CollectorResponseError(
                collector_error_message(
                    code=CollectorResponseError.code,
                    reason="feed response is not valid JSON",
                    retryable=CollectorResponseError.retryable,
                )
            ) from exc

        if not isinstance(payload, list):
            raise CollectorResponseError(
                collector_error_message(
                    code=CollectorResponseError.code,
                    reason="feed response is not a JSON array",
                    retryable=CollectorResponseError.retryable,
                )
            )

        story_ids: list[int] = []
        for item in payload:
            if not isinstance(item, int):
                raise CollectorResponseError(
                    collector_error_message(
                        code=CollectorResponseError.code,
                        reason="feed response array contains non-integer values",
                        retryable=CollectorResponseError.retryable,
                    )
                )
            story_ids.append(item)
        return story_ids

    def decode_item(self, body: bytes, *, source_id: str) -> RawObservation | None:
        if not body or not body.strip():
            return None

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise CollectorResponseError(
                collector_error_message(
                    code=CollectorResponseError.code,
                    reason=f"item {source_id} response is not valid JSON",
                    retryable=CollectorResponseError.retryable,
                )
            ) from exc

        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise CollectorResponseError(
                collector_error_message(
                    code=CollectorResponseError.code,
                    reason=f"item {source_id} response is not a JSON object",
                    retryable=CollectorResponseError.retryable,
                )
            )

        return payload


class FetchErrorClassifier:
    _RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

    def classify_feed_failure(
        self,
        *,
        exc: Exception | None = None,
        status_code: int | None = None,
    ) -> CollectorError:
        if exc is not None:
            if self._is_timeout(exc):
                return CollectorTimeoutError(
                    collector_error_message(
                        code=CollectorTimeoutError.code,
                        reason="feed fetch exceeded deadline",
                        retryable=CollectorTimeoutError.retryable,
                    )
                )
            if self.is_fatal_transport(exc):
                return CollectorFetchError(
                    collector_error_message(
                        code=CollectorFetchError.code,
                        reason="feed transport connection failed",
                        retryable=CollectorFetchError.retryable,
                    )
                )

        if status_code is not None:
            if status_code in self._RETRYABLE_HTTP_STATUSES:
                return CollectorFetchError(
                    collector_error_message(
                        code=CollectorFetchError.code,
                        reason=f"feed HTTP status {status_code}",
                        retryable=CollectorFetchError.retryable,
                    )
                )
            if 400 <= status_code < 500:
                return CollectorResponseError(
                    collector_error_message(
                        code=CollectorResponseError.code,
                        reason=f"feed HTTP status {status_code}",
                        retryable=CollectorResponseError.retryable,
                    )
                )
            if status_code >= 500:
                return CollectorFetchError(
                    collector_error_message(
                        code=CollectorFetchError.code,
                        reason=f"feed HTTP status {status_code}",
                        retryable=CollectorFetchError.retryable,
                    )
                )

        return CollectorFetchError(
            collector_error_message(
                code=CollectorFetchError.code,
                reason="feed fetch failed",
                retryable=CollectorFetchError.retryable,
            )
        )

    def classify_item_failure(
        self,
        result: ItemFetchResult,
    ) -> Literal["skip", "reject_json", "ok"]:
        if result.error_kind in {"timeout", "connection", "http"}:
            return "skip"

        if result.status_code != 200:
            return "skip"

        if result.body is None:
            return "ok"

        stripped = result.body.strip()
        if not stripped:
            return "ok"

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return "reject_json"

        if payload is None:
            return "ok"

        if not isinstance(payload, dict):
            return "reject_json"

        return "ok"

    def is_fatal_transport(self, exc: Exception) -> bool:
        if isinstance(exc, (ConnectionError, OSError)):
            return True
        return isinstance(exc, httpx.TransportError) and not isinstance(
            exc, httpx.TimeoutException
        )

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        return isinstance(exc, httpx.TimeoutException)


class FeedFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        decoder: ResponseDecoder,
        classifier: FetchErrorClassifier | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._decoder = decoder
        self._classifier = classifier or FetchErrorClassifier()

    def fetch(self) -> list[int]:
        url = f"{self._base_url}{TOP_STORIES_PATH}"
        try:
            response = self._client.get(url)
        except Exception as exc:
            raise self._classifier.classify_feed_failure(exc=exc) from exc

        if response.status_code != 200:
            raise self._classifier.classify_feed_failure(status_code=response.status_code)

        return self._decoder.decode_feed(response.content)


class ItemFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client,
        base_url: str,
        max_concurrency: int,
        decoder: ResponseDecoder,
        classifier: FetchErrorClassifier | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._max_concurrency = max_concurrency
        self._decoder = decoder
        self._classifier = classifier or FetchErrorClassifier()

    def fetch_all(self, story_ids: Sequence[int]) -> list[ItemFetchResult]:
        if not story_ids:
            return []

        results: list[ItemFetchResult | None] = [None] * len(story_ids)

        def fetch_one(index: int, story_id: int) -> tuple[int, ItemFetchResult]:
            source_id = str(story_id)
            url = f"{self._base_url}{ITEM_PATH_TEMPLATE.format(id=story_id)}"
            try:
                response = self._client.get(url)
            except Exception as exc:
                if self._classifier.is_fatal_transport(exc) and index == 0:
                    raise self._classifier.classify_feed_failure(exc=exc) from exc
                if self._classifier._is_timeout(exc):
                    return (
                        index,
                        ItemFetchResult(
                            source_id=source_id,
                            status_code=None,
                            body=None,
                            error_kind="timeout",
                        ),
                    )
                return (
                    index,
                    ItemFetchResult(
                        source_id=source_id,
                        status_code=None,
                        body=None,
                        error_kind="connection",
                    ),
                )

            if response.status_code != 200:
                return (
                    index,
                    ItemFetchResult(
                        source_id=source_id,
                        status_code=response.status_code,
                        body=response.content,
                        error_kind="http",
                    ),
                )

            return (
                index,
                ItemFetchResult(
                    source_id=source_id,
                    status_code=response.status_code,
                    body=response.content,
                    error_kind="none",
                ),
            )

        with ThreadPoolExecutor(max_workers=self._max_concurrency) as executor:
            futures = {
                executor.submit(fetch_one, index, story_id): index
                for index, story_id in enumerate(story_ids)
            }
            for future in as_completed(futures):
                index, result = future.result()
                results[index] = result

        return [result for result in results if result is not None]


class DefaultHackerNewsClient:
    def __init__(
        self,
        *,
        base_url: str = HN_BASE_URL,
        total_timeout: float = HTTP_TOTAL_TIMEOUT_SECONDS,
        connect_timeout: float = HTTP_CONNECT_TIMEOUT_SECONDS,
        max_concurrency: int = MAX_CONCURRENT_ITEM_FETCHES,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_concurrency = max_concurrency
        self._owns_client = http_client is None
        timeout = httpx.Timeout(total_timeout, connect=connect_timeout)
        self._client = http_client or httpx.Client(timeout=timeout)
        self._decoder = ResponseDecoder()
        self._classifier = FetchErrorClassifier()
        self._feed_fetcher = FeedFetcher(
            client=self._client,
            base_url=self._base_url,
            decoder=self._decoder,
            classifier=self._classifier,
        )
        self._item_fetcher = ItemFetcher(
            client=self._client,
            base_url=self._base_url,
            max_concurrency=max_concurrency,
            decoder=self._decoder,
            classifier=self._classifier,
        )

    def fetch_top_story_ids(self) -> FeedFetchResult:
        story_ids = self._feed_fetcher.fetch()
        return FeedFetchResult(story_ids=story_ids)

    def fetch_items(self, story_ids: Sequence[int]) -> list[ItemFetchResult]:
        return self._item_fetcher.fetch_all(story_ids)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> DefaultHackerNewsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
