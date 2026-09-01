"""COL-013 — public create_collector (PD-001)."""

from __future__ import annotations

import collector


def test_create_collector_importable_and_exported() -> None:
    assert "create_collector" in collector.__all__
    assert callable(collector.create_collector)


def test_create_collector_returns_distinct_instances_with_collect_stories() -> None:
    first = collector.create_collector()
    second = collector.create_collector()
    assert callable(getattr(first, "collect_stories", None))
    assert first is not second


def test_module_collect_stories_entry_still_works() -> None:
    assert callable(collector.collect_stories)
    assert "collect_stories" in collector.__all__
