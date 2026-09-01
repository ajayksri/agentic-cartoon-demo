"""Agents module public surface."""

from __future__ import annotations

from .errors import (
    AgentConfigurationError,
    AgentError,
    AgentInputValidationError,
    AgentOutputValidationError,
    AgentPromptLoadError,
)
from .protocols import CriticAgent, ScenarioGenerationAgent, TopicSelectionAgent
from .public_create import (
    create_critic_agent,
    create_scenario_generation_agent,
    create_topic_selection_agent,
)
from .types import (
    AgentRunContext,
    CandidateStory,
    CriticDimension,
    CriticInput,
    CriticIssue,
    CriticOutput,
    CriticStatus,
    EvaluationScores,
    ScenarioGenerationInput,
    ScenarioOutput,
    ScenarioPanel,
    TopicAlternative,
    TopicSelectionInput,
    TopicSelectionOutcome,
    TopicSelectionOutput,
    ValidationResult,
)

__version__ = "0.1.0-draft"

__all__ = [
    "__version__",
    "AgentConfigurationError",
    "AgentError",
    "AgentInputValidationError",
    "AgentOutputValidationError",
    "AgentPromptLoadError",
    "AgentRunContext",
    "CandidateStory",
    "CriticAgent",
    "CriticDimension",
    "CriticInput",
    "CriticIssue",
    "CriticOutput",
    "CriticStatus",
    "EvaluationScores",
    "ScenarioGenerationAgent",
    "ScenarioGenerationInput",
    "ScenarioOutput",
    "ScenarioPanel",
    "TopicAlternative",
    "TopicSelectionAgent",
    "TopicSelectionInput",
    "TopicSelectionOutcome",
    "TopicSelectionOutput",
    "ValidationResult",
    "create_critic_agent",
    "create_scenario_generation_agent",
    "create_topic_selection_agent",
]
