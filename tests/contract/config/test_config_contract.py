"""Contract tests CFG-TC-001 through CFG-TC-026 (CFG-011).

Imports ONLY from the config package public surface (`config.__init__`).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from config import (
    AgentId,
    ConfigCredentialMissingError,
    ConfigLoadError,
    ConfigMissingError,
    ConfigPromptNotFoundError,
    ConfigSecretDetectedError,
    ConfigValueError,
    InjectionId,
    ProviderId,
    TaskType,
    load_config,
)
from .helpers import (
    minimal_valid_config,
    seed_credentials,
    write_config,
)


@pytest.mark.cfg_tc("001")
def test_cfg_tc_001_reject_inline_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-001: inline secret heuristic rejects sk-... values.

    Requirements: ACD-CFG-001, ACD-SEC-001, MOD-CFG-INV-001
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for src, dst in prompt_files.items():
        (tmp_path / src).write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")

    config = minimal_valid_config()
    config["providers"]["openai"]["api_key_env"] = "sk-abcdefghijklmnopqrstuvwxyz"
    source = write_config(tmp_path, config)

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        load_config(source)

    assert exc_info.value.code == "CFG_SECRET"
    assert exc_info.value.key_path


@pytest.mark.cfg_tc("002")
def test_cfg_tc_002_accept_env_var_name_reference_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-002: api_key_env stores env var name, not secret value.

    Requirements: ACD-CFG-001, MOD-CFG-INV-003
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    source = write_config(tmp_path, minimal_valid_config())
    app_config = load_config(source)

    assert app_config.providers[ProviderId.OPENAI].api_key_env == "OPENAI_API_KEY"


@pytest.mark.cfg_tc("003")
def test_cfg_tc_003_independent_agent_provider_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-003: distinct provider and model per AgentId.

    Requirements: ACD-CFG-002
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    source = write_config(tmp_path, minimal_valid_config())
    app_config = load_config(source)

    assert app_config.get_agent_config(AgentId.TOPIC_SELECTOR).provider == ProviderId.GEMINI
    assert app_config.get_agent_config(AgentId.TOPIC_SELECTOR).model == "gemini-pro"
    assert app_config.get_agent_config(AgentId.SCENARIO_GENERATOR).provider == ProviderId.OPENAI
    assert app_config.get_agent_config(AgentId.SCENARIO_GENERATOR).model == "gpt-4"
    assert app_config.get_agent_config(AgentId.CRITIC).provider == ProviderId.ANTHROPIC
    assert app_config.get_agent_config(AgentId.CRITIC).model == "claude-3"


@pytest.mark.cfg_tc("004")
def test_cfg_tc_004_credential_required_only_for_configured_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-004: unused provider credentials not required.

    Requirements: ACD-SEC-002, MOD-CFG-INV-004
    """
    monkeypatch.chdir(tmp_path)
    config = minimal_valid_config()
    config["agents"]["topic_selector"]["provider"] = "gemini"
    config["agents"]["scenario_generator"]["provider"] = "gemini"
    config["agents"]["critic"]["provider"] = "gemini"
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-only")
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")

    source = write_config(tmp_path, config)
    load_config(source)


@pytest.mark.cfg_tc("005")
def test_cfg_tc_005_valid_candidate_count_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-005: collection.candidate_count exposed on AppConfig.

    Requirements: ACD-CFG-003
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    source = write_config(tmp_path, minimal_valid_config())
    app_config = load_config(source)

    assert app_config.collection.candidate_count == 10


@pytest.mark.parametrize("candidate_count", [0, -1])
@pytest.mark.cfg_tc("006")
def test_cfg_tc_006_invalid_candidate_count_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
    candidate_count: int,
) -> None:
    """CFG-TC-006: zero or negative candidate_count raises ConfigValueError.

    Requirements: ACD-CFG-003, MOD-CFG-INV-011
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    config = minimal_valid_config()
    config["collection"]["candidate_count"] = candidate_count
    source = write_config(tmp_path, config)

    with pytest.raises(ConfigValueError) as exc_info:
        load_config(source)

    assert exc_info.value.key_path == "collection.candidate_count"


@pytest.mark.cfg_tc("007")
def test_cfg_tc_007_valid_and_invalid_max_scenario_revisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-007: max_scenario_revisions positive required.

    Requirements: ACD-CFG-004
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    valid = write_config(tmp_path, minimal_valid_config())
    assert load_config(valid).workflow.max_scenario_revisions == 2

    invalid_config = minimal_valid_config()
    invalid_config["workflow"]["max_scenario_revisions"] = 0
    invalid = write_config(tmp_path, invalid_config)

    with pytest.raises(ConfigValueError):
        load_config(invalid)


@pytest.mark.cfg_tc("008")
def test_cfg_tc_008_worker_concurrency_per_agent_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-008: get_worker_concurrency returns configured value.

    Requirements: ACD-CFG-005
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    assert app_config.get_worker_concurrency(AgentId.TOPIC_SELECTOR) == 2


@pytest.mark.cfg_tc("009")
def test_cfg_tc_009_retry_policy_per_task_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-009: get_retry_policy exposes task retry settings.

    Requirements: ACD-CFG-005
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    assert app_config.get_retry_policy(TaskType.COLLECT).max_attempts == 3


@pytest.mark.cfg_tc("010")
def test_cfg_tc_010_invalid_retry_values_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-010: zero max_attempts raises ConfigValueError.

    Requirements: ACD-CFG-005
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    config = minimal_valid_config()
    config["retry"]["GENERATE_SCENARIO"]["max_attempts"] = 0
    source = write_config(tmp_path, config)

    with pytest.raises(ConfigValueError):
        load_config(source)


@pytest.mark.cfg_tc("011")
def test_cfg_tc_011_timeout_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-011: positive read_seconds required; zero rejected.

    Requirements: ACD-CFG-005, ACD-INT-004
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))
    assert app_config.timeouts[ProviderId.OPENAI].read_seconds > 0

    bad = minimal_valid_config()
    bad["timeouts"]["openai"]["read_seconds"] = 0
    with pytest.raises(ConfigValueError):
        load_config(write_config(tmp_path, bad))


@pytest.mark.cfg_tc("012")
def test_cfg_tc_012_rate_limit_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-012: rate_limit_per_minute exposed on ProviderConfig.

    Requirements: ACD-CFG-006
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    config = minimal_valid_config()
    config["providers"]["openai"]["rate_limit_per_minute"] = 60
    app_config = load_config(write_config(tmp_path, config))

    assert app_config.providers[ProviderId.OPENAI].rate_limit_per_minute == 60


@pytest.mark.cfg_tc("013")
def test_cfg_tc_013_optional_pricing_omitted_without_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-013: missing pricing blocks are valid.

    Requirements: ACD-CFG-006
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    for provider in (ProviderId.OPENAI, ProviderId.ANTHROPIC, ProviderId.GEMINI):
        assert app_config.providers[provider].pricing is None


@pytest.mark.cfg_tc("014")
def test_cfg_tc_014_select_active_injection_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-014: enabled injections selectively active.

    Requirements: ACD-CFG-007, MOD-CFG-INV-017
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    config = minimal_valid_config()
    config["failure_injection"] = {
        "enabled": True,
        "active_injections": ["FINJ-WKR-PRE", "FINJ-Q-DUP"],
    }
    app_config = load_config(write_config(tmp_path, config))

    assert app_config.is_injection_active(InjectionId.FINJ_WKR_PRE) is True
    assert app_config.is_injection_active(InjectionId.FINJ_PRV_ERROR) is False


@pytest.mark.cfg_tc("015")
def test_cfg_tc_015_disabled_injection_and_unknown_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-015: disabled ignores list; unknown ID fails validation.

    Requirements: ACD-CFG-007, MOD-CFG-INV-017, MOD-CFG-INV-018
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    disabled = minimal_valid_config()
    disabled["failure_injection"] = {
        "enabled": False,
        "active_injections": ["FINJ-WKR-PRE"],
    }
    app_config = load_config(write_config(tmp_path, disabled))
    assert app_config.is_injection_active(InjectionId.FINJ_WKR_PRE) is False

    unknown = minimal_valid_config()
    unknown["failure_injection"] = {
        "enabled": True,
        "active_injections": ["FINJ-UNKNOWN"],
    }
    with pytest.raises(ConfigValueError):
        load_config(write_config(tmp_path, unknown))


@pytest.mark.cfg_tc("016")
def test_cfg_tc_016_prompt_file_path_referenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-016: AgentConfig.prompt_file set for each agent.

    Requirements: ACD-CFG-008
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    expected_prompt_files = {
        AgentId.TOPIC_SELECTOR: "prompts/topic_selector/v1.txt",
        AgentId.SCENARIO_GENERATOR: "prompts/scenario_generator/v1.txt",
        AgentId.CRITIC: "prompts/critic/v1.txt",
    }
    for agent_id, prompt_file in expected_prompt_files.items():
        assert app_config.get_agent_config(agent_id).prompt_file == prompt_file


@pytest.mark.cfg_tc("017")
def test_cfg_tc_017_missing_prompt_file_fails_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CFG-TC-017: missing prompt file raises ConfigPromptNotFoundError.

    Requirements: ACD-CFG-008
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)

    config = minimal_valid_config()
    config["agents"]["topic_selector"]["prompt_file"] = "prompts/missing.txt"
    source = write_config(tmp_path, config)

    with pytest.raises(ConfigPromptNotFoundError) as exc_info:
        load_config(source)

    assert exc_info.value.prompt_file == "prompts/missing.txt"


@pytest.mark.cfg_tc("018")
def test_cfg_tc_018_postgresql_parameters_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-018: postgres connection parameters on AppConfig.

    Requirements: ACD-CFG-009
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))
    postgres = app_config.infrastructure.postgres

    assert postgres.host == "localhost"
    assert postgres.port == 5432
    assert postgres.database == "cartoon"
    assert postgres.user_env == "POSTGRES_USER"
    assert postgres.password_env == "POSTGRES_PASSWORD"


@pytest.mark.cfg_tc("019")
def test_cfg_tc_019_redis_parameters_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-019: redis connection parameters on AppConfig.

    Requirements: ACD-CFG-009
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    redis = load_config(write_config(tmp_path, minimal_valid_config())).infrastructure.redis

    assert redis.host == "localhost"
    assert redis.port == 6379


@pytest.mark.cfg_tc("020")
def test_cfg_tc_020_actionable_validation_error_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-020: missing required key yields ConfigMissingError with key_path.

    Requirements: ACD-CFG-010, MOD-CFG-INV-006
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    config = minimal_valid_config()
    del config["workflow"]["max_scenario_revisions"]
    source = write_config(tmp_path, config)

    with pytest.raises(ConfigMissingError) as exc_info:
        load_config(source)

    assert "workflow.max_scenario_revisions" in exc_info.value.key_path
    message = str(exc_info.value)
    assert "Required key is missing" in message
    assert "Expected:" in message
    assert "present key" in message


@pytest.mark.cfg_tc("021")
def test_cfg_tc_021_unparseable_source_fails_load(tmp_path: Path) -> None:
    """CFG-TC-021: corrupt YAML raises ConfigLoadError.

    Requirements: ACD-CFG-010
    """
    source = write_config(tmp_path, "{{not valid yaml")

    with pytest.raises(ConfigLoadError):
        load_config(source)


@pytest.mark.cfg_tc("022")
def test_cfg_tc_022_immutability_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-022: AppConfig and nested dataclasses are frozen.

    Requirements: MOD-CFG-INV-007
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    with pytest.raises(FrozenInstanceError):
        app_config.collection.candidate_count = 99  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        app_config.infrastructure.postgres.host = "other-host"  # type: ignore[misc]


@pytest.mark.cfg_tc("023")
def test_cfg_tc_023_missing_credential_for_configured_provider_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-023: missing OPENAI_API_KEY when openai agent configured.

    Requirements: ACD-SEC-002
    """
    monkeypatch.chdir(tmp_path)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic")
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        load_config(write_config(tmp_path, minimal_valid_config()))

    assert exc_info.value.env_var_name == "OPENAI_API_KEY"
    assert "openai-test-key" not in str(exc_info.value)


@pytest.mark.cfg_tc("024")
def test_cfg_tc_024_resolve_credential_returns_env_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-024: resolve_credential returns environment value.

    Requirements: ACD-CFG-002, MOD-CFG-INV-002
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-value")
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))

    assert app_config.resolve_credential("OPENAI_API_KEY") == "test-value"


@pytest.mark.cfg_tc("025")
def test_cfg_tc_025_resolve_credential_error_omits_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-025: missing env var raises ConfigCredentialMissingError.

    Requirements: MOD-CFG-INV-002
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    app_config = load_config(write_config(tmp_path, minimal_valid_config()))
    monkeypatch.delenv("MISSING_KEY", raising=False)

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        app_config.resolve_credential("MISSING_KEY")

    assert exc_info.value.env_var_name == "MISSING_KEY"


@pytest.mark.cfg_tc("026")
def test_cfg_tc_026_repeated_load_produces_equivalent_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt_files: dict[str, Path],
) -> None:
    """CFG-TC-026: successive loads yield value-equal AppConfig.

    Requirements: contract.md §3.1
    """
    monkeypatch.chdir(tmp_path)
    seed_credentials(monkeypatch)
    for rel in prompt_files:
        (tmp_path / rel).write_text("prompt\n", encoding="utf-8")

    source = write_config(tmp_path, minimal_valid_config())
    first = load_config(source)
    second = load_config(source)

    assert first == second
