"""Approval review projection from workflow output packages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from api.types import WorkflowOutputResponse

_REVIEW_PACKAGE_KEYS = frozenset({"topic", "scenario", "critic"})


@dataclass(frozen=True, slots=True)
class PanelReview:
    """Single cartoon panel for human approval review."""

    index: int
    scene: str | None
    dialogue: str | None


@dataclass(frozen=True, slots=True)
class ApprovalReview:
    """Human-approval-facing slice of a workflow output package."""

    workflow_id: str
    topic_selected: str | None
    topic_rationale: str | None
    scenario_artifact_id: str | None
    scenario_logical_version: int | None
    premise: str | None
    characters: tuple[str, ...]
    panels: tuple[PanelReview, ...]
    punchline: str | None
    critic_verdict: str | None
    critic_dimensions: tuple[tuple[str, str], ...]


def build_approval_review(response: WorkflowOutputResponse) -> ApprovalReview:
    """Project API output package fields needed for scenario approval."""
    package = response.package
    topic = _section(package, "topic")
    scenario = _section(package, "scenario")
    critic = _section(package, "critic")

    return ApprovalReview(
        workflow_id=response.workflow_id,
        topic_selected=_optional_str(topic.get("selected_topic")),
        topic_rationale=_first_str(topic, "rationale", "why_interesting"),
        scenario_artifact_id=_optional_str(scenario.get("artifact_id")),
        scenario_logical_version=_optional_int(scenario.get("logical_version")),
        premise=_optional_str(scenario.get("premise")),
        characters=_characters(scenario.get("characters")),
        panels=_panels(scenario.get("panels")),
        punchline=_optional_str(scenario.get("punchline")),
        critic_verdict=_first_str(critic, "verdict", "status"),
        critic_dimensions=_dimensions_or_issues(
            critic.get("dimensions"),
            critic.get("issues"),
        ),
    )


def format_approval_review(review: ApprovalReview) -> str:
    """Render approval review as plain text for stdout."""
    lines: list[str] = [
        f"workflow_id: {review.workflow_id}",
    ]
    if review.scenario_artifact_id is not None:
        lines.append(f"scenario_artifact_id: {review.scenario_artifact_id}")
    if review.scenario_logical_version is not None:
        lines.append(f"scenario_logical_version: {review.scenario_logical_version}")
    lines.append("")

    lines.append("topic:")
    lines.append(_field_line("selected_topic", review.topic_selected))
    lines.append(_field_line("rationale", review.topic_rationale))
    lines.append("")

    lines.append("scenario:")
    lines.append(_field_line("premise", review.premise))
    if review.characters:
        lines.append(f"  characters: {', '.join(review.characters)}")
    else:
        lines.append("  characters: (not available yet)")
    for panel in review.panels:
        lines.append(f"  panel {panel.index}:")
        lines.append(_field_line("scene", panel.scene, indent=4))
        lines.append(_field_line("dialogue", panel.dialogue, indent=4))
    if not review.panels:
        lines.append("  panels: (not available yet)")
    lines.append(_field_line("punchline", review.punchline))
    lines.append("")

    lines.append("critic:")
    lines.append(_field_line("verdict", review.critic_verdict))
    if review.critic_dimensions:
        lines.append("  dimensions:")
        for key, value in review.critic_dimensions:
            lines.append(f"    {key}: {value}")
    elif review.critic_verdict is not None:
        lines.append("  dimensions: (none)")
    else:
        lines.append("  dimensions: (not available yet)")

    return "\n".join(lines) + "\n"


def _section(package: Mapping[str, object], key: str) -> dict[str, Any]:
    if key not in _REVIEW_PACKAGE_KEYS:
        return {}
    value = package.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _characters(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                names.append(stripped)
        elif isinstance(item, dict):
            name = _optional_str(item.get("name"))
            if name is not None:
                names.append(name)
    return tuple(names)


def _panels(value: object) -> tuple[PanelReview, ...]:
    if not isinstance(value, list):
        return ()
    panels: list[PanelReview] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        panels.append(
            PanelReview(
                index=index,
                scene=_first_str(item, "scene", "caption"),
                dialogue=_optional_str(item.get("dialogue")),
            )
        )
    return tuple(panels)


def _first_str(mapping: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _optional_str(mapping.get(key))
        if value is not None:
            return value
    return None


def _dimensions_or_issues(
    dimensions: object,
    issues: object,
) -> tuple[tuple[str, str], ...]:
    pairs = _dimensions(dimensions)
    if pairs:
        return pairs
    if not isinstance(issues, list):
        return ()
    rendered: list[tuple[str, str]] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        dimension = _optional_str(item.get("dimension"))
        description = _optional_str(item.get("description"))
        if dimension is not None and description is not None:
            rendered.append((dimension, description))
    return tuple(rendered)


def _dimensions(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        return ()
    pairs: list[tuple[str, str]] = []
    for key in sorted(value):
        rendered = _optional_str(value[key])
        if rendered is not None:
            pairs.append((str(key), rendered))
    return tuple(pairs)


def _field_line(label: str, value: str | None, *, indent: int = 2) -> str:
    prefix = " " * indent
    if value is None:
        return f"{prefix}{label}: (not available yet)"
    return f"{prefix}{label}: {value}"
