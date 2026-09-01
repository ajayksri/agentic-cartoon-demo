"""Pre-code test mold for AGT-005 — SchemaValidator (LLD §4.7, §8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import AgentOutputValidationError
from config.types import AgentId


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agents" / "outputs"
_PROMPT_VERSION = "fixturever01"
_TOPIC_AGENT = AgentId.TOPIC_SELECTOR


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_schemas_loaded_at_import() -> None:
    from agents.validation import schema as schema_module

    assert hasattr(schema_module, "_SCHEMAS")
    keys = set(schema_module._SCHEMAS.keys())
    assert {"topic_selection", "scenario", "critic"}.issubset(keys)


def test_empty_content_raises_output_validation_error() -> None:
    from agents.validation.schema import SchemaValidator

    validator = SchemaValidator()
    with pytest.raises(AgentOutputValidationError):
        validator.parse_provider_content("   ", agent_id=_TOPIC_AGENT)


def test_oversized_content_raises_output_validation_error() -> None:
    from agents.constants import RESPONSE_CONTENT_MAX_BYTES
    from agents.validation.schema import SchemaValidator

    validator = SchemaValidator()
    oversized = "x" * (RESPONSE_CONTENT_MAX_BYTES + 1)
    with pytest.raises(AgentOutputValidationError):
        validator.parse_provider_content(oversized, agent_id=_TOPIC_AGENT)


def test_fenced_json_parsed_via_extract_json_payload() -> None:
    from agents.validation.schema import SchemaValidator

    body = _load("topic_selected_valid.json")
    wrapped = f"```json\n{body}\n```"
    payload = SchemaValidator().parse_provider_content(wrapped, agent_id=_TOPIC_AGENT)
    assert payload.data["outcome"] == "topic_selected"


def test_topic_selected_output_has_seven_score_dimensions() -> None:
    """AGT-TC-002: seven evaluation score fields required."""
    from agents.validation.schema import SchemaValidator

    payload = SchemaValidator().parse_provider_content(
        _load("topic_selected_valid.json"),
        agent_id=_TOPIC_AGENT,
    )
    output = SchemaValidator().validate_topic_output(
        payload,
        prompt_version=_PROMPT_VERSION,
    )
    scores = output.scores
    assert scores is not None
    assert scores.technical_relevance == pytest.approx(0.85)
    assert scores.developer_relevance == pytest.approx(0.9)
    assert scores.discussion_interest == pytest.approx(0.75)
    assert scores.humour_potential == pytest.approx(0.8)
    assert scores.irony_contradiction == pytest.approx(0.6)
    assert scores.visual_scenario_potential == pytest.approx(0.85)
    assert scores.background_knowledge_required == pytest.approx(0.4)


def test_no_suitable_topic_nullability_enforced() -> None:
    """CG-AGT-003: NO_SUITABLE_TOPIC clears topic fields and alternatives."""
    from agents import TopicSelectionOutcome
    from agents.validation.schema import SchemaValidator

    payload = SchemaValidator().parse_provider_content(
        _load("no_suitable_topic.json"),
        agent_id=_TOPIC_AGENT,
    )
    output = SchemaValidator().validate_topic_output(
        payload,
        prompt_version=_PROMPT_VERSION,
    )
    assert output.outcome == TopicSelectionOutcome.NO_SUITABLE_TOPIC
    assert output.selected_topic is None
    assert output.why_interesting is None
    assert output.cartoon_angle is None
    assert output.scores is None
    assert output.alternatives == ()


def test_scenario_panel_count_bounds_enforced() -> None:
    from agents.validation.schema import SchemaValidator

    body = json.loads(_load("scenario_valid.json"))
    body["panels"] = body["panels"][:2]
    payload = SchemaValidator().parse_provider_content(
        json.dumps(body),
        agent_id=AgentId.SCENARIO_GENERATOR,
    )
    with pytest.raises(AgentOutputValidationError):
        SchemaValidator().validate_scenario_output(payload, prompt_version=_PROMPT_VERSION)


def test_invalid_critic_status_raises_validation_error() -> None:
    """AGT-TC-033: status must be PASS or REVISE."""
    from agents.validation.schema import SchemaValidator

    body = json.loads(_load("critic_revise_valid.json"))
    body["status"] = "MAYBE"
    payload = SchemaValidator().parse_provider_content(
        json.dumps(body),
        agent_id=AgentId.CRITIC,
    )
    with pytest.raises(AgentOutputValidationError):
        SchemaValidator().validate_critic_output(payload, prompt_version=_PROMPT_VERSION)


def test_prompt_version_from_argument_not_model_json() -> None:
    """MOD-AGT-INV-011: prompt_version injected at construction, not from JSON."""
    from agents.validation.schema import SchemaValidator

    body = json.loads(_load("topic_selected_valid.json"))
    body["prompt_version"] = "model-emitted-version"
    payload = SchemaValidator().parse_provider_content(
        json.dumps(body),
        agent_id=_TOPIC_AGENT,
    )
    with pytest.raises(AgentOutputValidationError):
        SchemaValidator().validate_topic_output(payload, prompt_version=_PROMPT_VERSION)


def test_executable_strings_parsed_as_data_only() -> None:
    """AGT-TC-045: json.loads only — no eval/exec."""
    from agents.validation.schema import SchemaValidator

    body = json.loads(_load("topic_selected_valid.json"))
    body["selected_topic"] = "__import__('os').system('rm -rf /')"
    payload = SchemaValidator().parse_provider_content(
        json.dumps(body),
        agent_id=_TOPIC_AGENT,
    )
    output = SchemaValidator().validate_topic_output(payload, prompt_version=_PROMPT_VERSION)
    assert output.selected_topic == "__import__('os').system('rm -rf /')"
