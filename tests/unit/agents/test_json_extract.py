"""Pre-code test mold for AGT-002 — extract_json_payload (LLD §4.6)."""

from __future__ import annotations

import json

import pytest


_BARE_OBJECT = '{"outcome":"topic_selected","selected_topic":"Rust"}'
_BARE_ARRAY = '[{"scene":"office","dialogue":"hi"}]'


def test_bare_json_object_returned_unchanged() -> None:
    from agents.validation.json_extract import extract_json_payload

    assert extract_json_payload(_BARE_OBJECT) == _BARE_OBJECT


def test_bare_json_array_returned_unchanged() -> None:
    from agents.validation.json_extract import extract_json_payload

    assert extract_json_payload(_BARE_ARRAY) == _BARE_ARRAY


def test_fenced_json_without_language_tag() -> None:
    from agents.validation.json_extract import extract_json_payload

    wrapped = f"```\n{_BARE_OBJECT}\n```"
    assert extract_json_payload(wrapped) == _BARE_OBJECT


def test_fenced_json_with_language_tag() -> None:
    from agents.validation.json_extract import extract_json_payload

    wrapped = f"```json\n{_BARE_OBJECT}\n```"
    assert extract_json_payload(wrapped) == _BARE_OBJECT


def test_opening_fence_without_closing_uses_best_effort_remainder() -> None:
    from agents.validation.json_extract import extract_json_payload

    wrapped = f"```json\n{_BARE_OBJECT}"
    result = extract_json_payload(wrapped)
    parsed = json.loads(result)
    assert parsed["outcome"] == "topic_selected"


def test_outer_whitespace_stripped() -> None:
    from agents.validation.json_extract import extract_json_payload

    assert extract_json_payload(f"  {_BARE_OBJECT}  ") == _BARE_OBJECT
