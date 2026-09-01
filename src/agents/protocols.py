"""Public agent protocol definitions."""

from __future__ import annotations

from typing import Protocol

from .types import (
    AgentRunContext,
    CriticInput,
    CriticOutput,
    ScenarioGenerationInput,
    ScenarioOutput,
    TopicSelectionInput,
    TopicSelectionOutput,
)


class TopicSelectionAgent(Protocol):
    """Evaluate candidates and return validated topic selection output."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: TopicSelectionInput,
    ) -> TopicSelectionOutput:
        ...


class ScenarioGenerationAgent(Protocol):
    """Convert selected topic into a validated scenario."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: ScenarioGenerationInput,
    ) -> ScenarioOutput:
        ...


class CriticAgent(Protocol):
    """Review scenario and return validated critic verdict."""

    def run(
        self,
        *,
        context: AgentRunContext,
        input: CriticInput,
    ) -> CriticOutput:
        ...
