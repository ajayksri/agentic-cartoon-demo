"""Unit tests for COL-002 — pool sizing (LLD §3)."""

from __future__ import annotations

import pytest

from collector.constants import (
    POOL_SIZE_MAX,
    POOL_SIZE_MIN,
    POOL_SIZE_MULTIPLIER,
    compute_pool_size,
)


@pytest.mark.parametrize(
    ("candidate_count", "expected"),
    [
        (0, POOL_SIZE_MIN),
        (1, POOL_SIZE_MIN),
        (10, POOL_SIZE_MIN),
        (11, 55),
        (20, 100),
        (40, POOL_SIZE_MAX),
        (50, POOL_SIZE_MAX),
        (100, POOL_SIZE_MAX),
    ],
    ids=[
        "zero_candidates",
        "below_min_multiplier",
        "at_min_multiplier_boundary",
        "just_above_min_multiplier",
        "mid_range",
        "at_max_multiplier",
        "above_max_multiplier",
        "far_above_max",
    ],
)
def test_compute_pool_size_boundaries(candidate_count: int, expected: int) -> None:
    assert compute_pool_size(candidate_count) == expected
    assert POOL_SIZE_MIN <= expected <= POOL_SIZE_MAX
    assert expected == min(
        POOL_SIZE_MAX,
        max(POOL_SIZE_MIN, candidate_count * POOL_SIZE_MULTIPLIER),
    )
