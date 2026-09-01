"""Pre-code test mold for COL-003 — FetchErrorClassifier (LLD §4.5, §6)."""

from __future__ import annotations

import json

import pytest



def test_classify_feed_failure_connection_is_retryable_fetch() -> None:
    """DNS/connection failure maps to CollectorFetchError COL_FETCH retryable=True."""
    from collector.errors import CollectorFetchError
    from collector.hn_client import FetchErrorClassifier

    classifier = FetchErrorClassifier()

    error = classifier.classify_feed_failure(exc=ConnectionError("connection refused"))

    assert isinstance(error, CollectorFetchError)
    assert error.code == "COL_FETCH"
    assert error.retryable is True


@pytest.mark.parametrize("status_code", [500, 503, 408, 429])
def test_classify_feed_failure_retryable_http(status_code: int) -> None:
    """Feed HTTP 5xx/408/429 maps to CollectorFetchError (COL-TC-001)."""
    from collector.errors import CollectorFetchError
    from collector.hn_client import FetchErrorClassifier

    classifier = FetchErrorClassifier()
    error = classifier.classify_feed_failure(status_code=status_code)

    assert isinstance(error, CollectorFetchError)
    assert error.code == "COL_FETCH"
    assert error.retryable is True


@pytest.mark.parametrize("status_code", [400, 404])
def test_classify_feed_failure_permanent_http(status_code: int) -> None:
    """Feed HTTP 4xx (not 408/429) maps to CollectorResponseError (COL-TC-002)."""
    from collector.errors import CollectorResponseError
    from collector.hn_client import FetchErrorClassifier

    classifier = FetchErrorClassifier()
    error = classifier.classify_feed_failure(status_code=status_code)

    assert isinstance(error, CollectorResponseError)
    assert error.code == "COL_RESPONSE"
    assert error.retryable is False


def test_classify_feed_failure_timeout() -> None:
    """Total deadline exceeded maps to CollectorTimeoutError COL_TIMEOUT."""
    from collector.errors import CollectorTimeoutError
    from collector.hn_client import FetchErrorClassifier

    classifier = FetchErrorClassifier()
    error = classifier.classify_feed_failure(exc=TimeoutError("deadline exceeded"))

    assert isinstance(error, CollectorTimeoutError)
    assert error.code == "COL_TIMEOUT"
    assert error.retryable is True


def test_classify_item_failure_skip_on_transport_error() -> None:
    """Item HTTP error/timeout encodes as skip — no rejection."""
    from collector.hn_client import FetchErrorClassifier, ItemFetchResult

    classifier = FetchErrorClassifier()
    result = ItemFetchResult(
        source_id="1",
        status_code=503,
        body=None,
        error_kind="http",
    )

    assert classifier.classify_item_failure(result) == "skip"


def test_classify_item_failure_reject_json_on_invalid_body() -> None:
    """HTTP 200 with invalid JSON body encodes as reject_json."""
    from collector.hn_client import FetchErrorClassifier, ItemFetchResult

    classifier = FetchErrorClassifier()
    result = ItemFetchResult(
        source_id="2",
        status_code=200,
        body=b"not-json",
        error_kind="none",
    )

    assert classifier.classify_item_failure(result) == "reject_json"


def test_classify_item_failure_ok_on_valid_json() -> None:
    """HTTP 200 with valid JSON object encodes as ok."""
    from collector.hn_client import FetchErrorClassifier, ItemFetchResult

    classifier = FetchErrorClassifier()
    result = ItemFetchResult(
        source_id="3",
        status_code=200,
        body=json.dumps({"id": 3, "type": "story"}).encode("utf-8"),
        error_kind="none",
    )

    assert classifier.classify_item_failure(result) == "ok"


def test_is_fatal_transport_detects_connection_errors() -> None:
    """Fatal transport helper returns True for connection-level failures."""
    from collector.hn_client import FetchErrorClassifier

    classifier = FetchErrorClassifier()

    assert classifier.is_fatal_transport(ConnectionError("reset")) is True
