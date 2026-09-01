"""Unit tests for COL-003 — ItemFetcher feed-order preservation (LLD §4.3)."""

from __future__ import annotations

import time

import httpx


def test_item_fetcher_preserves_feed_order_under_concurrent_completion() -> None:
    """Item results match input story_ids order, not HTTP completion order."""
    from collector.hn_client import ItemFetcher, ResponseDecoder

    story_ids = [101, 102, 103]
    delays = {101: 0.05, 102: 0.0, 103: 0.0}

    def handler(request: httpx.Request) -> httpx.Response:
        story_id = int(request.url.path.rsplit("/", 1)[-1])
        time.sleep(delays.get(story_id, 0.0))
        return httpx.Response(200, json={"id": story_id, "type": "story"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="https://hacker-news.firebaseio.com",
    )
    fetcher = ItemFetcher(
        client=client,
        base_url="https://hacker-news.firebaseio.com",
        max_concurrency=3,
        decoder=ResponseDecoder(),
    )

    results = fetcher.fetch_all(story_ids)

    assert [int(result.source_id) for result in results] == story_ids
