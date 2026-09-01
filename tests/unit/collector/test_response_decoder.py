"""Pre-code test mold for COL-003 — ResponseDecoder (LLD §4.4)."""

from __future__ import annotations

import json

import pytest



def test_decode_feed_parses_int_array() -> None:
    """Valid feed JSON array of ints decodes to ordered ID list."""
    from collector.hn_client import ResponseDecoder

    body = json.dumps([1, 2, 3]).encode("utf-8")
    decoder = ResponseDecoder()

    assert decoder.decode_feed(body) == [1, 2, 3]


def test_decode_feed_rejects_invalid_json() -> None:
    """Invalid JSON raises CollectorResponseError (COL-TC-002 feed path)."""
    from collector.errors import CollectorResponseError
    from collector.hn_client import ResponseDecoder

    decoder = ResponseDecoder()

    with pytest.raises(CollectorResponseError) as exc_info:
        decoder.decode_feed(b"not-json")

    assert exc_info.value.code == "COL_RESPONSE"
    assert exc_info.value.retryable is False


def test_decode_feed_rejects_non_array_top_level() -> None:
    """Top-level object (not array) raises CollectorResponseError."""
    from collector.errors import CollectorResponseError
    from collector.hn_client import ResponseDecoder

    body = json.dumps({"ids": [1, 2]}).encode("utf-8")
    decoder = ResponseDecoder()

    with pytest.raises(CollectorResponseError) as exc_info:
        decoder.decode_feed(body)

    assert exc_info.value.code == "COL_RESPONSE"


def test_decode_item_returns_observation_dict() -> None:
    """Valid item JSON object decodes to raw observation mapping."""
    from collector.hn_client import ResponseDecoder

    payload = {"id": 42, "type": "story", "title": "Hello"}
    body = json.dumps(payload).encode("utf-8")
    decoder = ResponseDecoder()

    observation = decoder.decode_item(body, source_id="42")

    assert observation is not None
    assert observation["id"] == 42
    assert observation["title"] == "Hello"


def test_decode_item_null_json_returns_none() -> None:
    """JSON null body returns None (skip path in orchestration)."""
    from collector.hn_client import ResponseDecoder

    decoder = ResponseDecoder()

    assert decoder.decode_item(b"null", source_id="99") is None


def test_decode_item_empty_body_returns_none() -> None:
    """Empty body returns None without raising."""
    from collector.hn_client import ResponseDecoder

    decoder = ResponseDecoder()

    assert decoder.decode_item(b"", source_id="100") is None
