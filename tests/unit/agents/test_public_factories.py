"""AGT-015 — public create_* helpers (PD-001)."""

from __future__ import annotations

import agents


def test_create_topic_selection_agent_returns_runnable_distinct_instances() -> None:
    first = agents.create_topic_selection_agent()
    second = agents.create_topic_selection_agent()
    assert callable(getattr(first, "run", None))
    assert first is not second


def test_create_scenario_generation_agent_returns_runnable_distinct_instances() -> None:
    first = agents.create_scenario_generation_agent()
    second = agents.create_scenario_generation_agent()
    assert callable(getattr(first, "run", None))
    assert first is not second


def test_create_critic_agent_returns_runnable_distinct_instances() -> None:
    first = agents.create_critic_agent()
    second = agents.create_critic_agent()
    assert callable(getattr(first, "run", None))
    assert first is not second


def test_public_create_helpers_exported_and_agent_factory_not() -> None:
    for name in (
        "create_topic_selection_agent",
        "create_scenario_generation_agent",
        "create_critic_agent",
    ):
        assert name in agents.__all__
        assert getattr(agents, name) is not None
    assert "AgentFactory" not in agents.__all__
    assert not hasattr(agents, "AgentFactory")
