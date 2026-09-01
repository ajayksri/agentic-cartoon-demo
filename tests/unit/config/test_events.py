"""Unit tests for CFG-003 — startup load events."""

from __future__ import annotations

from config.events import (
    ConfigLoadEvent,
    ConfigLoadFailureEvent,
    ConfigLoadStartEvent,
    ConfigLoadSuccessEvent,
    NoOpStartupLogger,
    StartupLogger,
)


class RecordingStartupLogger:
    """List-recording fake implementing StartupLogger."""

    def __init__(self) -> None:
        self.events: list[ConfigLoadEvent] = []

    def emit(self, event: ConfigLoadEvent) -> None:
        self.events.append(event)


def test_config_load_start_event_fields() -> None:
    event = ConfigLoadStartEvent(source_path="/etc/cartoon.yaml")
    assert event.source_path == "/etc/cartoon.yaml"


def test_config_load_success_event_with_version() -> None:
    event = ConfigLoadSuccessEvent(source_path="/etc/cartoon.yaml", config_version="1.0")
    assert event.source_path == "/etc/cartoon.yaml"
    assert event.config_version == "1.0"


def test_config_load_success_event_without_version() -> None:
    event = ConfigLoadSuccessEvent(source_path="/etc/cartoon.yaml", config_version=None)
    assert event.config_version is None


def test_config_load_failure_event_with_all_fields() -> None:
    event = ConfigLoadFailureEvent(
        source_path="/etc/cartoon.yaml",
        error_code="CFG_MISSING",
        key_path="agents.topic_selector.model",
        env_var_name=None,
    )
    assert event.error_code == "CFG_MISSING"
    assert event.key_path == "agents.topic_selector.model"
    assert event.env_var_name is None


def test_config_load_failure_event_defaults() -> None:
    event = ConfigLoadFailureEvent(
        source_path="/etc/cartoon.yaml",
        error_code="CFG_LOAD",
    )
    assert event.key_path is None
    assert event.env_var_name is None


def test_recording_startup_logger_captures_events() -> None:
    logger = RecordingStartupLogger()
    start = ConfigLoadStartEvent(source_path="/etc/cartoon.yaml")
    success = ConfigLoadSuccessEvent(source_path="/etc/cartoon.yaml", config_version="1.0")
    failure = ConfigLoadFailureEvent(
        source_path="/etc/cartoon.yaml",
        error_code="CFG_SECRET",
        key_path="providers.openai.api_key",
    )

    logger.emit(start)
    logger.emit(success)
    logger.emit(failure)

    assert logger.events == [start, success, failure]


def test_noop_startup_logger_accepts_all_variants() -> None:
    logger = NoOpStartupLogger()
    logger.emit(ConfigLoadStartEvent(source_path="/etc/cartoon.yaml"))
    logger.emit(ConfigLoadSuccessEvent(source_path="/etc/cartoon.yaml", config_version=None))
    logger.emit(
        ConfigLoadFailureEvent(
            source_path="/etc/cartoon.yaml",
            error_code="CFG_CREDENTIAL",
            env_var_name="OPENAI_API_KEY",
        )
    )
