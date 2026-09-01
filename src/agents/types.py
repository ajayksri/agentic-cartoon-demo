"""Public agent value types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.types import AgentId, AppConfig
    from observability.protocols import Logger, Meter, Tracer
    from providers.protocols import ModelProvider


class TopicSelectionOutcome(StrEnum):
    TOPIC_SELECTED = "topic_selected"
    NO_SUITABLE_TOPIC = "no_suitable_topic"


class CriticStatus(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"


class CriticDimension(StrEnum):
    TECHNICAL_ACCURACY = "technical_accuracy"
    SCENARIO_QUALITY = "scenario_quality"
    PUBLICATION_QUALITY = "publication_quality"


class ValidationResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CandidateStory:
    """Reduced candidate passed to topic selection (not full collection)."""

    source_id: str
    title: str | None = None
    url: str | None = None
    score: int | None = None
    comment_count: int | None = None
    rank_score: float | None = None


@dataclass(frozen=True, slots=True)
class TopicSelectionInput:
    candidates: tuple[CandidateStory, ...]


@dataclass(frozen=True, slots=True)
class EvaluationScores:
    """Seven evaluation dimensions from ACD-FR-004."""

    technical_relevance: float
    developer_relevance: float
    discussion_interest: float
    humour_potential: float
    irony_contradiction: float
    visual_scenario_potential: float
    background_knowledge_required: float


@dataclass(frozen=True, slots=True)
class TopicAlternative:
    topic: str
    rationale: str


@dataclass(frozen=True, slots=True)
class TopicSelectionOutput:
    outcome: TopicSelectionOutcome
    prompt_version: str
    selected_topic: str | None = None
    why_interesting: str | None = None
    cartoon_angle: str | None = None
    scores: EvaluationScores | None = None
    alternatives: tuple[TopicAlternative, ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioGenerationInput:
    topic: TopicSelectionOutput


@dataclass(frozen=True, slots=True)
class ScenarioPanel:
    scene: str
    dialogue: str


@dataclass(frozen=True, slots=True)
class ScenarioOutput:
    topic: str
    premise: str
    characters: tuple[str, ...]
    panels: tuple[ScenarioPanel, ...]
    punchline: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class CriticIssue:
    dimension: CriticDimension
    description: str


@dataclass(frozen=True, slots=True)
class CriticInput:
    scenario: ScenarioOutput
    revision_number: int


@dataclass(frozen=True, slots=True)
class CriticOutput:
    status: CriticStatus
    issues: tuple[CriticIssue, ...]
    suggested_changes: tuple[str, ...]
    prompt_version: str


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    """Per-invocation context supplied by worker; agents do not construct workflow state."""

    agent_id: AgentId
    workflow_id: str
    task_id: str
    task_attempt: int
    config: AppConfig
    provider: ModelProvider
    logger: Logger
    meter: Meter
    tracer: Tracer
