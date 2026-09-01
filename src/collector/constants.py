"""Internal HN defaults, pool sizing, and concurrency caps."""

from __future__ import annotations

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_PATH = "/topstories.json"
ITEM_PATH_TEMPLATE = "/item/{id}.json"

HTTP_TOTAL_TIMEOUT_SECONDS = 30.0
HTTP_CONNECT_TIMEOUT_SECONDS = 10.0
MAX_CONCURRENT_ITEM_FETCHES = 10

POOL_SIZE_MIN = 50
POOL_SIZE_MAX = 200
POOL_SIZE_MULTIPLIER = 5

REJECTION_LOG_SAMPLE_LIMIT = 100
ERROR_DETAIL_MAX_LENGTH = 200


def compute_pool_size(candidate_count: int) -> int:
    return min(
        POOL_SIZE_MAX,
        max(POOL_SIZE_MIN, candidate_count * POOL_SIZE_MULTIPLIER),
    )
