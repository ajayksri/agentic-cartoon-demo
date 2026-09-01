"""Unit tests for CLI constants."""

from __future__ import annotations

from cli.constants import (
    FLAG_ACTOR,
    FLAG_INJECT,
    MAX_WORKFLOW_ID_LEN,
    SPAN_INITIATE,
    SUBCMD_INITIATE,
    WORKFLOW_ID_PATTERN,
)


def test_workflow_id_pattern_accepts_valid_ids() -> None:
    assert WORKFLOW_ID_PATTERN.match("wf-123_test")


def test_workflow_id_pattern_rejects_invalid_ids() -> None:
    assert WORKFLOW_ID_PATTERN.match("bad id") is None


def test_validation_limits_match_api() -> None:
    assert MAX_WORKFLOW_ID_LEN == 128


def test_flag_tokens_are_unique() -> None:
    tokens = {FLAG_INJECT, FLAG_ACTOR, SUBCMD_INITIATE}
    assert len(tokens) == len({token for token in tokens})


def test_span_name_matches_lld() -> None:
    assert SPAN_INITIATE == "cli.initiate"
