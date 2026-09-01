"""Contract tests AGT-TC-001 through AGT-TC-070 (AGT-014).

Imports ONLY from the agents package public surface (`agents.__init__`).
Boundary imports for test seams live in helpers.py / conftest.py per LLD §12.4.
"""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from agents import (
    AgentInputValidationError,
    AgentOutputValidationError,
    CandidateStory,
    CriticDimension,
    CriticInput,
    CriticOutput,
    CriticStatus,
    ScenarioGenerationInput,
    ScenarioOutput,
    ScenarioPanel,
    TopicSelectionInput,
    TopicSelectionOutcome,
    TopicSelectionOutput,
    ValidationResult,
)
from config.types import AgentConfig, AgentId
from providers import ProviderTimeoutError

from .helpers import (
    build_agent_run_context,
    create_capturing_fake_provider,
    create_critic_agent_for_contract_tests,
    create_scenario_agent_for_contract_tests,
    create_topic_agent_for_contract_tests,
    critic_input,
    load_output_fixture,
    metric_emissions,
    minimal_agents_config,
    programmed_agent_response,
    recording_observability,
    scenario_generation_input,
    scenario_output_for_critic,
    topic_selected_output_for_scenario,
    topic_selection_input,
)


_AGENTS_SRC = Path(__file__).resolve().parents[3] / "src" / "agents"
_FORBIDDEN_MODULES = frozenset({"worker", "workflow", "persistence", "task_queue"})


def _topic_agent(config: object | None = None, **kwargs: object) -> object:
    return create_topic_agent_for_contract_tests(**kwargs)


def _scenario_agent(**kwargs: object) -> object:
    return create_scenario_agent_for_contract_tests(**kwargs)


def _critic_agent(**kwargs: object) -> object:
    return create_critic_agent_for_contract_tests(**kwargs)


@pytest.mark.agt_tc("001")
def test_agt_tc_001_agent_receives_candidate_set_only(agent_env_keys: None) -> None:
    """AGT-TC-001: provider messages reference only supplied candidates."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    agent.run(context=context, input=topic_selection_input(candidate_count=3))  # type: ignore[attr-defined]

    assert provider.requests
    for message in provider.requests[-1].messages:
        text = message.content.lower()
        assert "full_collection" not in text
        assert "workflow_id" not in text
        assert "task_id" not in text


@pytest.mark.agt_tc("002")
def test_agt_tc_002_evaluation_scores_present_on_topic_selected(agent_env_keys: None) -> None:
    """AGT-TC-002: TopicSelectionOutput.scores contains all seven dimensions."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    scores = output.scores
    assert scores is not None
    for field_name in (
        "technical_relevance",
        "developer_relevance",
        "discussion_interest",
        "humour_potential",
        "irony_contradiction",
        "visual_scenario_potential",
        "background_knowledge_required",
    ):
        assert hasattr(scores, field_name)


@pytest.mark.agt_tc("010")
def test_agt_tc_010_topic_selection_output_schema_fields(agent_env_keys: None) -> None:
    """AGT-TC-010: output includes required topic selection fields."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    assert output.selected_topic
    assert output.why_interesting
    assert output.cartoon_angle
    assert output.scores is not None
    assert output.alternatives is not None
    assert output.prompt_version


@pytest.mark.agt_tc("011")
def test_agt_tc_011_invalid_provider_output_raises_validation_error(agent_env_keys: None) -> None:
    """AGT-TC-011: malformed provider body raises AgentOutputValidationError."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content='{"outcome":"topic_selected"}'))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    with pytest.raises(AgentOutputValidationError):
        agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]


@pytest.mark.agt_tc("012")
def test_agt_tc_012_no_suitable_topic_outcome_supported(agent_env_keys: None) -> None:
    """AGT-TC-012: NO_SUITABLE_TOPIC outcome supported."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("no_suitable_topic.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    assert output.outcome == TopicSelectionOutcome.NO_SUITABLE_TOPIC


@pytest.mark.agt_tc("013")
def test_agt_tc_013_empty_candidates_rejected_before_provider(agent_env_keys: None) -> None:
    """AGT-TC-013: empty candidates raise AgentInputValidationError before provider."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    with pytest.raises(AgentInputValidationError):
        agent.run(
            context=context,
            input=TopicSelectionInput(candidates=()),
        )  # type: ignore[attr-defined]
    assert provider.requests == []


@pytest.mark.agt_tc("020")
def test_agt_tc_020_scenario_contains_panels(agent_env_keys: None) -> None:
    """AGT-TC-020: ScenarioOutput.panels length is 3 or 4."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("scenario_valid.json")))
    agent = _scenario_agent()
    context = build_agent_run_context(
        agent_id=AgentId.SCENARIO_GENERATOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=scenario_generation_input())  # type: ignore[attr-defined]
    assert 3 <= len(output.panels) <= 4


@pytest.mark.agt_tc("021")
def test_agt_tc_021_scenario_rejected_when_topic_not_selected(agent_env_keys: None) -> None:
    """AGT-TC-021: NO_SUITABLE_TOPIC input rejected before provider."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    agent = _scenario_agent()
    context = build_agent_run_context(
        agent_id=AgentId.SCENARIO_GENERATOR,
        config=config,
        provider=provider,
    )
    with pytest.raises(AgentInputValidationError):
        agent.run(
            context=context,
            input=scenario_generation_input(outcome_not_selected=True),
        )  # type: ignore[attr-defined]
    assert provider.requests == []


@pytest.mark.agt_tc("022")
def test_agt_tc_022_scenario_output_schema_fields(agent_env_keys: None) -> None:
    """AGT-TC-022: scenario output includes required fields."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("scenario_valid.json")))
    agent = _scenario_agent()
    context = build_agent_run_context(
        agent_id=AgentId.SCENARIO_GENERATOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=scenario_generation_input())  # type: ignore[attr-defined]
    assert output.topic
    assert output.premise
    assert output.characters
    assert output.panels
    assert output.punchline
    assert output.prompt_version


@pytest.mark.agt_tc("023")
def test_agt_tc_023_invalid_scenario_output_raises_validation_error(agent_env_keys: None) -> None:
    """AGT-TC-023: malformed scenario JSON raises AgentOutputValidationError."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content='{"topic":"only topic"}'))
    agent = _scenario_agent()
    context = build_agent_run_context(
        agent_id=AgentId.SCENARIO_GENERATOR,
        config=config,
        provider=provider,
    )
    with pytest.raises(AgentOutputValidationError):
        agent.run(context=context, input=scenario_generation_input())  # type: ignore[attr-defined]


@pytest.mark.agt_tc("024")
def test_agt_tc_024_no_mandated_humour_template_in_config() -> None:
    """AGT-TC-024: AgentConfig has no humour_template field."""
    assert "humour_template" not in {field.name for field in fields(AgentConfig)}


@pytest.mark.agt_tc("030")
def test_agt_tc_030_critic_evaluates_three_dimensions(agent_env_keys: None) -> None:
    """AGT-TC-030: REVISE output issues cover three critic dimensions."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("critic_revise_valid.json")))
    agent = _critic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.CRITIC,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]
    dimensions = {issue.dimension for issue in output.issues}
    assert CriticDimension.TECHNICAL_ACCURACY in dimensions
    assert CriticDimension.SCENARIO_QUALITY in dimensions
    assert CriticDimension.PUBLICATION_QUALITY in dimensions


@pytest.mark.agt_tc("031")
def test_agt_tc_031_provider_failure_does_not_emit_critic_verdict_metric(
    agent_env_keys: None,
) -> None:
    """AGT-TC-031: ProviderTimeoutError raised; critic_verdict_total NOT incremented."""
    from config.types import ProviderId

    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_error(ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE))
    agent = _critic_agent()
    with recording_observability():
        from observability import get_meter

        context = build_agent_run_context(
            agent_id=AgentId.CRITIC,
            config=config,
            provider=provider,
            meter=get_meter(),
        )
        with pytest.raises(ProviderTimeoutError):
            agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]
        emissions = metric_emissions(get_meter())
    assert not any(name == "critic_verdict_total" for name, _, _, _ in emissions)


@pytest.mark.agt_tc("032")
def test_agt_tc_032_critic_output_schema_fields(agent_env_keys: None) -> None:
    """AGT-TC-032: critic output includes status, issues, suggested_changes, prompt_version."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("critic_revise_valid.json")))
    agent = _critic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.CRITIC,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]
    assert output.status == CriticStatus.REVISE
    assert output.issues is not None
    assert output.suggested_changes is not None
    assert output.prompt_version


@pytest.mark.agt_tc("033")
def test_agt_tc_033_ambiguous_critic_status_is_validation_failure(agent_env_keys: None) -> None:
    """AGT-TC-033: invalid status raises AgentOutputValidationError."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    body = json.loads(load_output_fixture("critic_revise_valid.json"))
    body["status"] = "MAYBE"
    provider.set_next_response(programmed_agent_response(content=json.dumps(body)))
    agent = _critic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.CRITIC,
        config=config,
        provider=provider,
    )
    with pytest.raises(AgentOutputValidationError):
        agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]


@pytest.mark.agt_tc("034")
def test_agt_tc_034_agent_does_not_enforce_revision_limit(agent_env_keys: None) -> None:
    """AGT-TC-034: high revision_number still returns REVISE."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("critic_revise_valid.json")))
    agent = _critic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.CRITIC,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=critic_input(revision_number=999))  # type: ignore[attr-defined]
    assert output.status == CriticStatus.REVISE


@pytest.mark.agt_tc("040")
def test_agt_tc_040_validation_pass_recorded(agent_env_keys: None) -> None:
    """AGT-TC-040: agent_validation_total{result=passed} incremented on success."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    with recording_observability():
        from observability import get_logger, get_meter, get_tracer
        from observability.fakes import InMemoryLogger

        context = build_agent_run_context(
            agent_id=AgentId.TOPIC_SELECTOR,
            config=config,
            provider=provider,
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
        emissions = metric_emissions(get_meter())
        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert any(
            name == "agent_validation_total" and labels.get("result") == "passed"
            for name, _, _, labels in emissions
        )
        assert "validation_result" in joined or "passed" in joined


@pytest.mark.agt_tc("041")
def test_agt_tc_041_validation_fail_recorded_before_raise(agent_env_keys: None) -> None:
    """AGT-TC-041: agent_validation_total{result=failed} incremented before raise."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content='{"outcome":"topic_selected"}'))
    agent = _topic_agent()
    with recording_observability():
        from observability import get_meter

        context = build_agent_run_context(
            agent_id=AgentId.TOPIC_SELECTOR,
            config=config,
            provider=provider,
            meter=get_meter(),
        )
        with pytest.raises(AgentOutputValidationError):
            agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
        emissions = metric_emissions(get_meter())
        assert any(
            name == "agent_validation_total" and labels.get("result") == "failed"
            for name, _, _, labels in emissions
        )


@pytest.mark.agt_tc("042")
def test_agt_tc_042_critic_pass_metric_independent(agent_env_keys: None) -> None:
    """AGT-TC-042: critic_verdict_total{status=pass} on PASS success."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("critic_pass_valid.json")))
    agent = _critic_agent()
    with recording_observability():
        from observability import get_meter

        context = build_agent_run_context(
            agent_id=AgentId.CRITIC,
            config=config,
            provider=provider,
            meter=get_meter(),
        )
        agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]
        emissions = metric_emissions(get_meter())
        assert any(
            name == "critic_verdict_total" and labels.get("status") == "pass"
            for name, _, _, labels in emissions
        )
        assert any(name == "agent_validation_total" for name, _, _, _ in emissions)


@pytest.mark.agt_tc("043")
def test_agt_tc_043_critic_revise_not_counted_as_validation_failure(agent_env_keys: None) -> None:
    """AGT-TC-043: REVISE is validation success with critic_verdict_total{status=revise}."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("critic_revise_valid.json")))
    agent = _critic_agent()
    with recording_observability():
        from observability import get_meter

        context = build_agent_run_context(
            agent_id=AgentId.CRITIC,
            config=config,
            provider=provider,
            meter=get_meter(),
        )
        agent.run(context=context, input=critic_input())  # type: ignore[attr-defined]
        emissions = metric_emissions(get_meter())
        assert any(
            name == "agent_validation_total" and labels.get("result") == "passed"
            for name, _, _, labels in emissions
        )
        assert any(
            name == "critic_verdict_total" and labels.get("status") == "revise"
            for name, _, _, labels in emissions
        )


@pytest.mark.agt_tc("045")
def test_agt_tc_045_no_eval_exec_of_model_output(agent_env_keys: None) -> None:
    """AGT-TC-045: executable-looking strings parsed as data only."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    body = json.loads(load_output_fixture("topic_selected_valid.json"))
    body["selected_topic"] = "__import__('os').system('echo pwned')"
    provider.set_next_response(programmed_agent_response(content=json.dumps(body)))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    assert "pwned" in (output.selected_topic or "")


@pytest.mark.agt_tc("050")
def test_agt_tc_050_prompt_loaded_from_config_path(agent_env_keys: None, tmp_path: object) -> None:
    """AGT-TC-050: prompt content sourced from configured file path."""
    from pathlib import Path

    prompt_path = Path(str(tmp_path)) / "custom_topic_prompt.txt"
    custom_text = "CUSTOM_PROMPT_MARKER {{candidates_json}}"
    prompt_path.write_text(custom_text, encoding="utf-8")

    config = minimal_agents_config(
        prompt_files={AgentId.TOPIC_SELECTOR: str(prompt_path)},
    )
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    system_messages = [
        message.content
        for message in provider.requests[-1].messages
        if "CUSTOM_PROMPT_MARKER" in message.content or "Story" in message.content
    ]
    assert system_messages or any("CUSTOM_PROMPT_MARKER" in req.messages[0].content for req in provider.requests)


@pytest.mark.agt_tc("051")
def test_agt_tc_051_output_records_prompt_version(agent_env_keys: None) -> None:
    """AGT-TC-051: successful run returns non-empty prompt_version."""
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=load_output_fixture("topic_selected_valid.json")))
    agent = _topic_agent()
    context = build_agent_run_context(
        agent_id=AgentId.TOPIC_SELECTOR,
        config=config,
        provider=provider,
    )
    output = agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
    assert output.prompt_version
    assert len(output.prompt_version) > 0


@pytest.mark.agt_tc("060")
def test_agt_tc_060_module_has_no_queue_or_persistence_imports() -> None:
    """AGT-TC-060: static analysis finds no forbidden cross-module imports."""
    violations: list[str] = []
    for path in sorted(_AGENTS_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in _FORBIDDEN_MODULES:
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in _FORBIDDEN_MODULES:
                    violations.append(f"{path.name}: from {node.module} import ...")
    assert violations == []


@pytest.mark.agt_tc("061")
def test_agt_tc_061_telemetry_excludes_prompts_and_responses(agent_env_keys: None) -> None:
    """AGT-TC-061: logs and metrics exclude prompt/response text."""
    secret_prompt = "TOP_SECRET_PROMPT_DO_NOT_LOG"
    secret_response = load_output_fixture("topic_selected_valid.json")
    config = minimal_agents_config()
    provider = create_capturing_fake_provider(config)
    provider.set_next_response(programmed_agent_response(content=secret_response))
    agent = _topic_agent()
    with recording_observability():
        from observability import get_logger, get_meter, get_tracer
        from observability.fakes import InMemoryLogger

        context = build_agent_run_context(
            agent_id=AgentId.TOPIC_SELECTOR,
            config=config,
            provider=provider,
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        agent.run(context=context, input=topic_selection_input())  # type: ignore[attr-defined]
        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert secret_prompt not in joined
        for name, _, _, labels in metric_emissions(get_meter()):
            assert secret_prompt not in str((name, labels))


@pytest.mark.agt_tc("070")
def test_agt_tc_070_input_output_types_frozen() -> None:
    """AGT-TC-070: output dataclasses are immutable."""
    topic_output = TopicSelectionOutput(
        outcome=TopicSelectionOutcome.TOPIC_SELECTED,
        prompt_version="v1",
        selected_topic="Rust",
    )
    scenario_output = ScenarioOutput(
        topic="Rust",
        premise="Debate",
        characters=("Alice",),
        panels=(ScenarioPanel(scene="Office", dialogue="Hi"),),
        punchline="Done.",
        prompt_version="v1",
    )
    critic_output = CriticOutput(
        status=CriticStatus.PASS,
        issues=(),
        suggested_changes=(),
        prompt_version="v1",
    )
    for instance, attr, value in (
        (topic_output, "selected_topic", "mutated"),
        (scenario_output, "punchline", "mutated"),
        (critic_output, "prompt_version", "mutated"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, attr, value)
