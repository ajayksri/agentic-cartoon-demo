"""Startup load observability event shapes and logger protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ConfigLoadStartEvent:
    source_path: str


@dataclass(frozen=True, slots=True)
class ConfigLoadSuccessEvent:
    source_path: str
    config_version: str | None


@dataclass(frozen=True, slots=True)
class ConfigLoadFailureEvent:
    source_path: str
    error_code: str
    key_path: str | None = None
    env_var_name: str | None = None


ConfigLoadEvent = ConfigLoadStartEvent | ConfigLoadSuccessEvent | ConfigLoadFailureEvent


class StartupLogger(Protocol):
    def emit(self, event: ConfigLoadEvent) -> None: ...


class NoOpStartupLogger:
    def emit(self, event: ConfigLoadEvent) -> None:
        return None
