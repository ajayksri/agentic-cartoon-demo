"""Public configuration protocols."""

from __future__ import annotations

from typing import Protocol

from .types import AppConfig, ConfigSource


class ConfigLoader(Protocol):
    """Loads, validates, and returns immutable application configuration."""

    def load(self, source: ConfigSource | None = None) -> AppConfig:
        """Load configuration from the given source or the process default."""
        ...
