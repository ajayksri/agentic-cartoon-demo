"""Pre-code T0 molds for DefaultConfigLoader and SourceLocator (CFG-010)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from config.errors import (
    ConfigCredentialMissingError,
    ConfigLoadError,
    ConfigPromptNotFoundError,
    ConfigValueError,
)
from config.types import AppConfig, ConfigSource


class _RecordingStartupLogger:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


def test_source_locator_explicit_path_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit ConfigSource.path wins over env and default."""
    from config.loader import CONFIG_PATH_ENV_VAR, SourceLocator

    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("key: value\n", encoding="utf-8")
    default = tmp_path / "default.yaml"
    default.write_text("key: default\n", encoding="utf-8")

    monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(default))
    monkeypatch.chdir(tmp_path)

    locator = SourceLocator()
    resolved = locator.resolve(ConfigSource(path=explicit))

    assert resolved == explicit


def test_source_locator_env_var_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CARTOON_CONFIG_PATH used when explicit source path is absent."""
    from config.loader import CONFIG_PATH_ENV_VAR, SourceLocator

    env_path = tmp_path / "from_env.yaml"
    env_path.write_text("key: env\n", encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV_VAR, str(env_path))
    monkeypatch.chdir(tmp_path)

    locator = SourceLocator()
    resolved = locator.resolve(None)

    assert resolved == env_path


def test_source_locator_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conventional default config/cartoon.yaml relative to CWD."""
    from config.loader import DEFAULT_CONFIG_PATH, CONFIG_PATH_ENV_VAR, SourceLocator

    monkeypatch.delenv(CONFIG_PATH_ENV_VAR, raising=False)
    cwd = Path.cwd()
    default_file = cwd / DEFAULT_CONFIG_PATH
    default_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_text("key: default\n", encoding="utf-8")

    try:
        locator = SourceLocator()
        resolved = locator.resolve(None)
        assert resolved == default_file
    finally:
        if default_file.exists():
            default_file.unlink()
        if default_file.parent.exists() and not any(default_file.parent.iterdir()):
            default_file.parent.rmdir()


def test_source_locator_missing_file_raises_config_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CFG-TC-021 trace: unreadable/missing source raises ConfigLoadError."""
    from config.loader import SourceLocator

    missing = tmp_path / "missing.yaml"
    monkeypatch.chdir(tmp_path)

    locator = SourceLocator()

    with pytest.raises(ConfigLoadError):
        locator.resolve(ConfigSource(path=missing))


def test_load_orchestrates_pipeline_stages_in_order() -> None:
    """LLD §9: S1a → S1b → S2 → S3–S6 → factory build."""
    from config.loader import DefaultConfigLoader

    stage_log: list[str] = []
    fake_app_config = MagicMock(spec=AppConfig)

    class _Stage:
        def __init__(self, name: str) -> None:
            self.name = name

        def parse_file(self, path: Path) -> dict[str, object]:
            stage_log.append("S1a")
            return {}

        def scan(self, tree: dict[str, object]) -> None:
            stage_log.append("S1b")

        def map(self, tree: dict[str, object]) -> Any:
            stage_log.append("S2")
            return MagicMock()

        def validate(self, draft: Any) -> Any:
            stage_log.append("S3-S6")
            return draft

        def build(self, draft: Any) -> AppConfig:
            stage_log.append("factory")
            return fake_app_config

        def resolve(self, source: ConfigSource | None) -> Path:
            return Path("fixture.yaml")

    parser = _Stage("parser")
    scanner = _Stage("scanner")
    mapper = _Stage("mapper")
    validator = _Stage("validator")
    factory = _Stage("factory")
    locator = _Stage("locator")

    loader = DefaultConfigLoader(
        source_locator=locator,
        parser=parser,
        secret_scanner=scanner,
        schema_mapper=mapper,
        validator=validator,
        factory=factory,
        startup_logger=_RecordingStartupLogger(),
    )

    result = loader.load(ConfigSource(path=Path("fixture.yaml")))

    assert result is fake_app_config
    assert stage_log == ["S1a", "S1b", "S2", "S3-S6", "factory"]


def test_load_emits_startup_events_on_success() -> None:
    """Startup logger receives start and success events (LLD §5)."""
    from config.loader import DefaultConfigLoader

    logger = _RecordingStartupLogger()
    fake_app_config = MagicMock(spec=AppConfig)

    loader = DefaultConfigLoader(
        source_locator=MagicMock(resolve=MagicMock(return_value=Path("ok.yaml"))),
        parser=MagicMock(parse_file=MagicMock(return_value={})),
        secret_scanner=MagicMock(scan=MagicMock(return_value=None)),
        schema_mapper=MagicMock(map=MagicMock(return_value=MagicMock(config_version="1"))),
        validator=MagicMock(validate=MagicMock(side_effect=lambda d: d)),
        factory=MagicMock(build=MagicMock(return_value=fake_app_config)),
        startup_logger=logger,
    )

    loader.load(ConfigSource(path=Path("ok.yaml")))

    assert len(logger.events) == 2
    assert logger.events[0].__class__.__name__ == "ConfigLoadStartEvent"
    assert logger.events[1].__class__.__name__ == "ConfigLoadSuccessEvent"


def test_load_emits_failure_event_and_reraises() -> None:
    """Failure path emits ConfigLoadFailureEvent then re-raises original error."""
    from config.loader import DefaultConfigLoader

    logger = _RecordingStartupLogger()
    validation_error = ConfigValueError("invalid", key_path="collection.candidate_count")

    loader = DefaultConfigLoader(
        source_locator=MagicMock(resolve=MagicMock(return_value=Path("bad.yaml"))),
        parser=MagicMock(parse_file=MagicMock(return_value={})),
        secret_scanner=MagicMock(scan=MagicMock(return_value=None)),
        schema_mapper=MagicMock(map=MagicMock(return_value=MagicMock())),
        validator=MagicMock(validate=MagicMock(side_effect=validation_error)),
        factory=MagicMock(),
        startup_logger=logger,
    )

    with pytest.raises(ConfigValueError) as exc_info:
        loader.load(ConfigSource(path=Path("bad.yaml")))

    assert exc_info.value is validation_error
    assert len(logger.events) == 2
    assert logger.events[1].__class__.__name__ == "ConfigLoadFailureEvent"
    assert logger.events[1].error_code == "CFG_VALUE"
    assert logger.events[1].key_path == "collection.candidate_count"


def test_load_resolve_failure_emits_failure_event_without_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CFG-010-R001: resolve-stage ConfigLoadError emits failure event only."""
    from config.loader import DefaultConfigLoader

    missing = tmp_path / "missing.yaml"
    monkeypatch.chdir(tmp_path)
    logger = _RecordingStartupLogger()

    loader = DefaultConfigLoader(startup_logger=logger)

    with pytest.raises(ConfigLoadError):
        loader.load(ConfigSource(path=missing))

    assert len(logger.events) == 1
    assert logger.events[0].__class__.__name__ == "ConfigLoadFailureEvent"
    assert logger.events[0].source_path == str(missing)
    assert logger.events[0].error_code == "CFG_LOAD"
    assert logger.events[0].key_path is None
    assert logger.events[0].env_var_name is None


def test_load_emits_failure_event_for_credential_missing_error() -> None:
    """CFG-010-R002: ConfigCredentialMissingError maps env_var_name per LLD §5."""
    from config.loader import DefaultConfigLoader

    logger = _RecordingStartupLogger()
    credential_error = ConfigCredentialMissingError(
        "Required credential environment variable is unset or empty: OPENAI_API_KEY",
        env_var_name="OPENAI_API_KEY",
    )

    loader = DefaultConfigLoader(
        source_locator=MagicMock(resolve=MagicMock(return_value=Path("ok.yaml"))),
        parser=MagicMock(parse_file=MagicMock(return_value={})),
        secret_scanner=MagicMock(scan=MagicMock(return_value=None)),
        schema_mapper=MagicMock(map=MagicMock(return_value=MagicMock())),
        validator=MagicMock(validate=MagicMock(side_effect=credential_error)),
        factory=MagicMock(),
        startup_logger=logger,
    )

    with pytest.raises(ConfigCredentialMissingError) as exc_info:
        loader.load(ConfigSource(path=Path("ok.yaml")))

    assert exc_info.value is credential_error
    failure = logger.events[1]
    assert failure.__class__.__name__ == "ConfigLoadFailureEvent"
    assert failure.error_code == "CFG_CREDENTIAL"
    assert failure.key_path is None
    assert failure.env_var_name == "OPENAI_API_KEY"


def test_load_emits_failure_event_for_prompt_not_found_error() -> None:
    """CFG-010-R002: ConfigPromptNotFoundError maps key_path from message per LLD §5."""
    from config.loader import DefaultConfigLoader
    from config.messages import prompt_message

    logger = _RecordingStartupLogger()
    key_path = "agents.topic_selector.prompt_file"
    prompt_error = ConfigPromptNotFoundError(
        prompt_message(key_path=key_path, prompt_file="prompts/missing.txt"),
        prompt_file="prompts/missing.txt",
    )

    loader = DefaultConfigLoader(
        source_locator=MagicMock(resolve=MagicMock(return_value=Path("ok.yaml"))),
        parser=MagicMock(parse_file=MagicMock(return_value={})),
        secret_scanner=MagicMock(scan=MagicMock(return_value=None)),
        schema_mapper=MagicMock(map=MagicMock(return_value=MagicMock())),
        validator=MagicMock(validate=MagicMock(side_effect=prompt_error)),
        factory=MagicMock(),
        startup_logger=logger,
    )

    with pytest.raises(ConfigPromptNotFoundError) as exc_info:
        loader.load(ConfigSource(path=Path("ok.yaml")))

    assert exc_info.value is prompt_error
    failure = logger.events[1]
    assert failure.__class__.__name__ == "ConfigLoadFailureEvent"
    assert failure.error_code == "CFG_PROMPT"
    assert failure.key_path == key_path
    assert failure.env_var_name is None


def test_load_config_delegates_to_default_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public load_config delegates to module singleton loader."""
    from config import load_config
    from config.loader import DefaultConfigLoader

    sentinel = MagicMock(spec=AppConfig)
    fake_loader = MagicMock(spec=DefaultConfigLoader)
    fake_loader.load.return_value = sentinel
    monkeypatch.setattr("config.loader._DEFAULT_LOADER", fake_loader)

    source = ConfigSource(path=Path("delegated.yaml"))
    result = load_config(source)

    fake_loader.load.assert_called_once_with(source)
    assert result is sentinel


def test_each_load_rereads_source_no_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CFG-TC-026 trace: no module-level cache; each call re-reads."""
    from config.loader import DefaultConfigLoader

    config_file = tmp_path / "cartoon.yaml"
    config_file.write_text("version: 1\n", encoding="utf-8")
    read_count = {"n": 0}

    def _parse_file(path: Path) -> dict[str, object]:
        read_count["n"] += 1
        return {}

    loader = DefaultConfigLoader(
        source_locator=MagicMock(resolve=MagicMock(return_value=config_file)),
        parser=MagicMock(parse_file=_parse_file),
        secret_scanner=MagicMock(scan=MagicMock(return_value=None)),
        schema_mapper=MagicMock(map=MagicMock(return_value=MagicMock(config_version=None))),
        validator=MagicMock(validate=MagicMock(side_effect=lambda d: d)),
        factory=MagicMock(build=MagicMock(return_value=MagicMock(spec=AppConfig))),
        startup_logger=_RecordingStartupLogger(),
    )

    loader.load(ConfigSource(path=config_file))
    loader.load(ConfigSource(path=config_file))

    assert read_count["n"] == 2
