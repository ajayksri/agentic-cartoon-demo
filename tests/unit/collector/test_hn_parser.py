"""Pre-code test mold for COL-004 — HackerNewsParser (LLD §4.6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "collector"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_item_story_returns_parsed_observation() -> None:
    """Valid story type returns ('story', observation) with stable keys."""
    from collector.hn_parser import HackerNewsParser

    observation = _load_fixture("complete_story.json")
    parser = HackerNewsParser()

    parsed, outcome = parser.parse_item(observation)

    assert outcome == "story"
    assert parsed is not None
    assert parsed["id"] == 1001
    assert parsed["title"] == "Complete Story Title"


def test_parse_item_comment_type_skips() -> None:
    """Non-story type returns skip without side effects."""
    from collector.hn_parser import HackerNewsParser

    parser = HackerNewsParser()
    observation: dict[str, object] = {"id": 9, "type": "comment", "text": "reply"}

    parsed, outcome = parser.parse_item(observation)

    assert outcome == "skip"
    assert parsed is None


def test_parse_item_ask_type_skips() -> None:
    """Ask HN item type returns skip."""
    from collector.hn_parser import HackerNewsParser

    parser = HackerNewsParser()
    observation: dict[str, object] = {"id": 10, "type": "ask", "title": "Ask HN"}

    parsed, outcome = parser.parse_item(observation)

    assert outcome == "skip"
    assert parsed is None


def test_parse_item_deleted_story_rejects() -> None:
    """Deleted story flag returns reject_deleted."""
    from collector.hn_parser import HackerNewsParser

    parser = HackerNewsParser()
    observation: dict[str, object] = {
        "id": 11,
        "type": "story",
        "title": "Gone",
        "deleted": True,
    }

    parsed, outcome = parser.parse_item(observation)

    assert outcome == "reject_deleted"
    assert parsed is None


def test_source_id_from_pool_id_returns_string() -> None:
    """Pool integer IDs convert to stable string source_id."""
    from collector.hn_parser import HackerNewsParser

    parser = HackerNewsParser()

    assert parser.source_id_from_pool_id(424242) == "424242"
