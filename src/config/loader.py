"""Configuration load orchestration: source resolution and pipeline wiring."""

from __future__ import annotations

import os
from pathlib import Path

from config.app_config import AppConfigFactory
from config.credentials import CredentialResolver
from config.errors import (
    ConfigCredentialMissingError,
    ConfigError,
    ConfigLoadError,
    ConfigPromptNotFoundError,
)
from config.events import (
    ConfigLoadFailureEvent,
    ConfigLoadStartEvent,
    ConfigLoadSuccessEvent,
    NoOpStartupLogger,
    StartupLogger,
)
from config.parser import ConfigParser
from config.schema import SchemaMapper
from config.secrets import SecretScanner
from config.types import AppConfig, ConfigSource
from config.validator import ConfigValidator

DEFAULT_CONFIG_PATH = Path("config/cartoon.yaml")
CONFIG_PATH_ENV_VAR = "CARTOON_CONFIG_PATH"


def _select_config_path(source: ConfigSource | None) -> Path:
    """Return config path per explicit → env → default precedence (no existence check)."""
    if source is not None and source.path is not None:
        return source.path
    env_path = os.environ.get(CONFIG_PATH_ENV_VAR, "")
    if env_path:
        return Path(env_path)
    return Path.cwd() / DEFAULT_CONFIG_PATH


class SourceLocator:
    def resolve(self, source: ConfigSource | None) -> Path:
        """Resolve configuration file path using explicit, env, then default precedence."""
        path = _select_config_path(source)

        if not path.is_file():
            raise ConfigLoadError(
                f"Configuration file not found or not readable: {path}"
            )

        return path


def _failure_event_fields(exc: ConfigError) -> tuple[str | None, str | None]:
    if isinstance(exc, ConfigCredentialMissingError):
        return None, exc.env_var_name
    if isinstance(exc, ConfigPromptNotFoundError):
        message = str(exc)
        key_path = message.split(": ", 1)[0] if ": " in message else None
        return key_path, None
    key_path = getattr(exc, "key_path", None)
    return key_path, None


def _emit_failure_event(
    startup_logger: StartupLogger,
    *,
    source_path: str,
    exc: ConfigError,
) -> None:
    key_path, env_var_name = _failure_event_fields(exc)
    try:
        startup_logger.emit(
            ConfigLoadFailureEvent(
                source_path=source_path,
                error_code=exc.code,
                key_path=key_path,
                env_var_name=env_var_name,
            )
        )
    except Exception:
        pass


class DefaultConfigLoader:
    """Implements ConfigLoader protocol."""

    def __init__(
        self,
        *,
        source_locator: SourceLocator | None = None,
        parser: ConfigParser | None = None,
        secret_scanner: SecretScanner | None = None,
        schema_mapper: SchemaMapper | None = None,
        validator: ConfigValidator | None = None,
        factory: AppConfigFactory | None = None,
        startup_logger: StartupLogger | None = None,
    ) -> None:
        self._source_locator = source_locator or SourceLocator()
        self._parser = parser or ConfigParser()
        self._secret_scanner = secret_scanner or SecretScanner()
        self._schema_mapper = schema_mapper or SchemaMapper()
        self._validator = validator or ConfigValidator()
        self._factory = factory or AppConfigFactory(credential_resolver=CredentialResolver())
        self._startup_logger = startup_logger or NoOpStartupLogger()

    def load(self, source: ConfigSource | None = None) -> AppConfig:
        try:
            resolved = self._source_locator.resolve(source)
        except ConfigError as exc:
            _emit_failure_event(
                self._startup_logger,
                source_path=str(_select_config_path(source)),
                exc=exc,
            )
            raise

        source_path = str(resolved)
        self._startup_logger.emit(ConfigLoadStartEvent(source_path=source_path))

        try:
            tree = self._parser.parse_file(resolved)
            self._secret_scanner.scan(tree)
            draft = self._schema_mapper.map(tree)
            draft = self._validator.validate(draft)
            app_config = self._factory.build(draft)

            self._startup_logger.emit(
                ConfigLoadSuccessEvent(
                    source_path=source_path,
                    config_version=draft.config_version,
                )
            )
            return app_config
        except ConfigError as exc:
            _emit_failure_event(
                self._startup_logger,
                source_path=source_path,
                exc=exc,
            )
            raise


_DEFAULT_LOADER = DefaultConfigLoader(startup_logger=NoOpStartupLogger())


def load_config(source: ConfigSource | None = None) -> AppConfig:
    return _DEFAULT_LOADER.load(source)
