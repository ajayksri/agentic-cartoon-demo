"""Public production create helpers (PD-001 / AGT-015).

Wraps internal AgentFactory; do not export AgentFactory from the package.
"""

from __future__ import annotations

from .factory import AgentFactory
from .protocols import CriticAgent, ScenarioGenerationAgent, TopicSelectionAgent


def create_topic_selection_agent() -> TopicSelectionAgent:
    """Default topic-selection agent for worker composition."""
    return AgentFactory().create_topic_selector()


def create_scenario_generation_agent() -> ScenarioGenerationAgent:
    """Default scenario-generation agent for worker composition."""
    return AgentFactory().create_scenario_generator()


def create_critic_agent() -> CriticAgent:
    """Default critic agent for worker composition."""
    return AgentFactory().create_critic()
