"""Collector module public surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import (
    CollectorError,
    CollectorFetchError,
    CollectorResponseError,
    CollectorTimeoutError,
)
from .protocols import Collector
from .types import (
    CollectionResult,
    CollectionStats,
    RejectedStoryRecord,
    RejectionReason,
    StoryRecord,
    StorySource,
)

if TYPE_CHECKING:
    from config.types import AppConfig

__version__ = "0.1.0-draft"


def collect_stories(*, config: AppConfig) -> CollectionResult:
    """Primary public entry point. Delegates to the default Collector implementation."""
    from .service import collect_stories as _collect_stories

    return _collect_stories(config=config)


def create_collector() -> Collector:
    """Return the default Collector implementation for composition (PD-001)."""
    from .service import DefaultCollector

    return DefaultCollector()


__all__ = [
    "__version__",
    "CollectionResult",
    "CollectionStats",
    "Collector",
    "CollectorError",
    "CollectorFetchError",
    "CollectorResponseError",
    "CollectorTimeoutError",
    "RejectedStoryRecord",
    "RejectionReason",
    "StoryRecord",
    "StorySource",
    "collect_stories",
    "create_collector",
]
