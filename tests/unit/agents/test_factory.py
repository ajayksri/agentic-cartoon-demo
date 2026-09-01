"""Pre-code test mold for AGT-013 — AgentFactory (LLD §4.1)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


_AGENTS_INIT = Path(__file__).resolve().parents[3] / "src" / "agents" / "__init__.py"


def test_create_methods_return_distinct_instances() -> None:
    from agents.factory import AgentFactory

    factory = AgentFactory()
    first_topic = factory.create_topic_selector()
    second_topic = factory.create_topic_selector()
    assert first_topic is not second_topic

    first_scenario = factory.create_scenario_generator()
    second_scenario = factory.create_scenario_generator()
    assert first_scenario is not second_scenario

    first_critic = factory.create_critic()
    second_critic = factory.create_critic()
    assert first_critic is not second_critic


def test_create_agent_for_tests_accepts_injectable_collaborators() -> None:
    from agents.base import AgentStage
    from agents.factory import _create_agent_for_tests

    class _StubPromptLoader:
        def load(self, prompt_file: str, *, agent_id: object) -> object:
            from agents.prompts.loader import PromptLoadResult

            return PromptLoadResult(text="stub", version="stubver", path=prompt_file)

    class _StubSchemaValidator:
        pass

    agent = _create_agent_for_tests(
        stage=AgentStage.TOPIC_SELECTION,
        prompt_loader=_StubPromptLoader(),
        schema_validator=_StubSchemaValidator(),
    )
    assert agent is not None


def test_factory_not_exported_from_public_init() -> None:
    source = _AGENTS_INIT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    exported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for element in node.value.elts:
                            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                                exported_names.add(element.value)
    assert "AgentFactory" not in exported_names
    assert "_create_agent_for_tests" not in exported_names
    assert "factory" not in source
