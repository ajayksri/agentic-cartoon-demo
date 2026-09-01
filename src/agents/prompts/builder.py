"""Mustache substitution and stage-specific provider messages."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from config.types import AgentId

from agents.errors import AgentPromptLoadError
from agents.messages import prompt_load_message
from agents.types import CandidateStory, CriticInput, ScenarioGenerationInput, TopicSelectionInput
from providers.types import ProviderMessage, ProviderMessageRole

_MUSTACHE_PATTERN = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_REMAINING_MUSTACHE = re.compile(r"\{\{[^}]+\}\}")


def _candidate_to_dict(candidate: CandidateStory) -> dict[str, object]:
    payload: dict[str, object] = {"source_id": candidate.source_id}
    for field_name in ("title", "url", "score", "comment_count", "rank_score"):
        value = getattr(candidate, field_name)
        if value is not None:
            payload[field_name] = value
    return payload


def _scenario_to_dict(scenario: object) -> dict[str, object]:
    from agents.types import ScenarioOutput

    assert isinstance(scenario, ScenarioOutput)
    return {
        "topic": scenario.topic,
        "premise": scenario.premise,
        "characters": list(scenario.characters),
        "panels": [{"scene": panel.scene, "dialogue": panel.dialogue} for panel in scenario.panels],
        "punchline": scenario.punchline,
    }


class MessageBuilder:
    """Builds SYSTEM/USER provider message tuples per agent stage."""

    def build_topic_messages(
        self,
        *,
        prompt_text: str,
        input: TopicSelectionInput,
        agent_id: AgentId,
    ) -> tuple[ProviderMessage, ...]:
        candidates_json = json.dumps(
            [_candidate_to_dict(candidate) for candidate in input.candidates],
            separators=(",", ":"),
        )
        system_content = self._substitute_mustache(
            prompt_text,
            {"candidates_json": candidates_json},
            agent_id=agent_id,
        )
        return (
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content=system_content),
            ProviderMessage(role=ProviderMessageRole.USER, content=candidates_json),
        )

    def build_scenario_messages(
        self,
        *,
        prompt_text: str,
        input: ScenarioGenerationInput,
        agent_id: AgentId,
    ) -> tuple[ProviderMessage, ...]:
        topic = input.topic
        variables = {
            "selected_topic": topic.selected_topic or "",
            "why_interesting": topic.why_interesting or "",
            "cartoon_angle": topic.cartoon_angle or "",
        }
        system_content = self._substitute_mustache(
            prompt_text,
            variables,
            agent_id=agent_id,
        )
        user_payload = json.dumps(
            {
                "selected_topic": topic.selected_topic,
                "why_interesting": topic.why_interesting,
                "cartoon_angle": topic.cartoon_angle,
            },
            separators=(",", ":"),
        )
        return (
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content=system_content),
            ProviderMessage(role=ProviderMessageRole.USER, content=user_payload),
        )

    def build_critic_messages(
        self,
        *,
        prompt_text: str,
        input: CriticInput,
        agent_id: AgentId,
    ) -> tuple[ProviderMessage, ...]:
        scenario_json = json.dumps(_scenario_to_dict(input.scenario), separators=(",", ":"))
        revision_number = str(input.revision_number)
        system_content = self._substitute_mustache(
            prompt_text,
            {"scenario_json": scenario_json, "revision_number": revision_number},
            agent_id=agent_id,
        )
        user_payload = json.dumps(
            {
                "scenario": _scenario_to_dict(input.scenario),
                "revision_number": input.revision_number,
            },
            separators=(",", ":"),
        )
        return (
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content=system_content),
            ProviderMessage(role=ProviderMessageRole.USER, content=user_payload),
        )

    def _substitute_mustache(
        self,
        template: str,
        variables: Mapping[str, str],
        *,
        agent_id: AgentId,
    ) -> str:
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in variables:
                return match.group(0)
            return variables[key]

        substituted = _MUSTACHE_PATTERN.sub(_replace, template)
        if _REMAINING_MUSTACHE.search(substituted):
            raise AgentPromptLoadError(
                prompt_load_message(
                    agent_id=agent_id,
                    reason="unresolved template variables",
                ),
                agent_id=agent_id,
            )
        return substituted
