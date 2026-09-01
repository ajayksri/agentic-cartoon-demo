"""Public collector protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .types import CollectionResult

if TYPE_CHECKING:
    from config.types import AppConfig


class Collector(Protocol):
    """Fetch, normalize, rank, and reduce Hacker News stories to candidates."""

    def collect_stories(self, *, config: AppConfig) -> CollectionResult:
        """Run one collection cycle using the supplied application configuration."""
        ...
