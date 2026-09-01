"""JSON schema validation and provider output parsing."""

# GUARDRAIL: Output — LLM responses must pass JSON schema validation before entering workflow.

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

import jsonschema

from config.types import AgentId

from agents.constants import (
    CRITIC_ISSUE_DESCRIPTION_MAX,
    MAX_JSON_DEPTH,
    RESPONSE_CONTENT_MAX_BYTES,
    SCENARIO_PANEL_MAX,
    SCENARIO_PANEL_MIN,
    SCORE_MAX,
    SCORE_MIN,
)
from agents.errors import AgentOutputValidationError
from agents.messages import output_validation_message
from agents.types import (
    CriticDimension,
    CriticIssue,
    CriticOutput,
    CriticStatus,
    EvaluationScores,
    ScenarioOutput,
    ScenarioPanel,
    TopicAlternative,
    TopicSelectionOutcome,
    TopicSelectionOutput,
)
from agents.validation.json_extract import extract_json_payload


def _load_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    schemas_root = resources.files("agents").joinpath("schemas")
    for key in ("topic_selection", "scenario", "critic"):
        raw = schemas_root.joinpath(f"{key}.json").read_text(encoding="utf-8")
        schemas[key] = json.loads(raw)
    return schemas


_SCHEMAS: dict[str, dict[str, Any]] = _load_schemas()


@dataclass(frozen=True, slots=True)
class ParsedProviderPayload:
    """Parsed dict after JSON extraction; before dataclass construction."""

    data: dict[str, object]
    raw_length: int


def _max_json_depth(
    obj: object,
    *,
    limit: int = MAX_JSON_DEPTH,
    depth: int = 0,
) -> None:
    if depth > limit:
        msg = f"JSON depth exceeds {limit}"
        raise AgentOutputValidationError(msg)
    if isinstance(obj, dict):
        for value in obj.values():
            _max_json_depth(value, limit=limit, depth=depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _max_json_depth(item, limit=limit, depth=depth + 1)


def _raise_output_error(*, agent_id: AgentId, reason: str) -> None:
    raise AgentOutputValidationError(
        output_validation_message(agent_id=agent_id, reason=reason),
        agent_id=agent_id,
    )


def _validate_score_range(value: object, *, field_name: str, agent_id: AgentId) -> float:
    if not isinstance(value, (int, float)):
        _raise_output_error(agent_id=agent_id, reason=f"invalid score for {field_name}")
    score = float(value)
    if score < SCORE_MIN or score > SCORE_MAX:
        _raise_output_error(
            agent_id=agent_id,
            reason=f"score {field_name} outside {SCORE_MIN}..{SCORE_MAX}",
        )
    return score


class SchemaValidator:
    """Validates provider JSON output against stage schemas."""

    def parse_provider_content(
        self,
        content: str,
        *,
        agent_id: AgentId,
    ) -> ParsedProviderPayload:
        if len(content) > RESPONSE_CONTENT_MAX_BYTES:
            _raise_output_error(
                agent_id=agent_id,
                reason="response content exceeds size limit",
            )
        if content.strip() == "":
            _raise_output_error(agent_id=agent_id, reason="empty content")

        payload_str = extract_json_payload(content)
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            _raise_output_error(
                agent_id=agent_id,
                reason=f"invalid JSON: {exc.msg}",
            )

        if not isinstance(data, dict):
            _raise_output_error(agent_id=agent_id, reason="JSON root must be object")

        _max_json_depth(data)
        return ParsedProviderPayload(data=data, raw_length=len(content))

    def validate_topic_output(
        self,
        payload: ParsedProviderPayload,
        *,
        prompt_version: str,
    ) -> TopicSelectionOutput:
        agent_id = AgentId.TOPIC_SELECTOR
        data = payload.data
        try:
            jsonschema.validate(instance=data, schema=_SCHEMAS["topic_selection"])
        except jsonschema.ValidationError as exc:
            _raise_output_error(agent_id=agent_id, reason=str(exc.message))

        outcome = TopicSelectionOutcome(str(data["outcome"]))

        if outcome == TopicSelectionOutcome.TOPIC_SELECTED:
            scores_raw = data.get("scores")
            if not isinstance(scores_raw, dict):
                _raise_output_error(agent_id=agent_id, reason="missing scores")
            scores = EvaluationScores(
                technical_relevance=_validate_score_range(
                    scores_raw["technical_relevance"],
                    field_name="technical_relevance",
                    agent_id=agent_id,
                ),
                developer_relevance=_validate_score_range(
                    scores_raw["developer_relevance"],
                    field_name="developer_relevance",
                    agent_id=agent_id,
                ),
                discussion_interest=_validate_score_range(
                    scores_raw["discussion_interest"],
                    field_name="discussion_interest",
                    agent_id=agent_id,
                ),
                humour_potential=_validate_score_range(
                    scores_raw["humour_potential"],
                    field_name="humour_potential",
                    agent_id=agent_id,
                ),
                irony_contradiction=_validate_score_range(
                    scores_raw["irony_contradiction"],
                    field_name="irony_contradiction",
                    agent_id=agent_id,
                ),
                visual_scenario_potential=_validate_score_range(
                    scores_raw["visual_scenario_potential"],
                    field_name="visual_scenario_potential",
                    agent_id=agent_id,
                ),
                background_knowledge_required=_validate_score_range(
                    scores_raw["background_knowledge_required"],
                    field_name="background_knowledge_required",
                    agent_id=agent_id,
                ),
            )
            alternatives_raw = data.get("alternatives", [])
            alternatives = tuple(
                TopicAlternative(topic=str(item["topic"]), rationale=str(item["rationale"]))
                for item in alternatives_raw
                if isinstance(item, dict)
            )
            return TopicSelectionOutput(
                outcome=outcome,
                prompt_version=prompt_version,
                selected_topic=str(data["selected_topic"]),
                why_interesting=str(data["why_interesting"]),
                cartoon_angle=str(data["cartoon_angle"]),
                scores=scores,
                alternatives=alternatives,
            )

        return TopicSelectionOutput(
            outcome=outcome,
            prompt_version=prompt_version,
            selected_topic=None,
            why_interesting=None,
            cartoon_angle=None,
            scores=None,
            alternatives=(),
        )

    def validate_scenario_output(
        self,
        payload: ParsedProviderPayload,
        *,
        prompt_version: str,
    ) -> ScenarioOutput:
        agent_id = AgentId.SCENARIO_GENERATOR
        data = payload.data
        try:
            jsonschema.validate(instance=data, schema=_SCHEMAS["scenario"])
        except jsonschema.ValidationError as exc:
            _raise_output_error(agent_id=agent_id, reason=str(exc.message))

        panels_raw = data.get("panels", [])
        if not isinstance(panels_raw, list):
            _raise_output_error(agent_id=agent_id, reason="panels must be an array")
        panel_count = len(panels_raw)
        if panel_count < SCENARIO_PANEL_MIN or panel_count > SCENARIO_PANEL_MAX:
            _raise_output_error(
                agent_id=agent_id,
                reason=f"panel count {panel_count} outside {SCENARIO_PANEL_MIN}..{SCENARIO_PANEL_MAX}",
            )

        panels = tuple(
            ScenarioPanel(scene=str(panel["scene"]), dialogue=str(panel["dialogue"]))
            for panel in panels_raw
            if isinstance(panel, dict)
        )
        characters_raw = data.get("characters", [])
        characters = tuple(str(character) for character in characters_raw)

        return ScenarioOutput(
            topic=str(data["topic"]),
            premise=str(data["premise"]),
            characters=characters,
            panels=panels,
            punchline=str(data["punchline"]),
            prompt_version=prompt_version,
        )

    def validate_critic_output(
        self,
        payload: ParsedProviderPayload,
        *,
        prompt_version: str,
    ) -> CriticOutput:
        agent_id = AgentId.CRITIC
        data = payload.data
        try:
            jsonschema.validate(instance=data, schema=_SCHEMAS["critic"])
        except jsonschema.ValidationError as exc:
            _raise_output_error(agent_id=agent_id, reason=str(exc.message))

        status = CriticStatus(str(data["status"]))
        if status not in (CriticStatus.PASS, CriticStatus.REVISE):
            _raise_output_error(agent_id=agent_id, reason="invalid critic status")

        issues_raw = data.get("issues", [])
        issues: list[CriticIssue] = []
        if isinstance(issues_raw, list):
            for item in issues_raw:
                if not isinstance(item, dict):
                    continue
                description = str(item.get("description", ""))
                if len(description) > CRITIC_ISSUE_DESCRIPTION_MAX:
                    _raise_output_error(
                        agent_id=agent_id,
                        reason="issue description exceeds max length",
                    )
                issues.append(
                    CriticIssue(
                        dimension=CriticDimension(str(item["dimension"])),
                        description=description,
                    ),
                )

        suggested_raw = data.get("suggested_changes", [])
        suggested_changes = (
            tuple(str(change) for change in suggested_raw)
            if isinstance(suggested_raw, list)
            else ()
        )

        return CriticOutput(
            status=status,
            issues=tuple(issues),
            suggested_changes=suggested_changes,
            prompt_version=prompt_version,
        )
