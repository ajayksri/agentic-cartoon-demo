"""Shared unit-test helpers for runtime molds."""

from __future__ import annotations

from config.types import AppConfig

from tests.contract.worker.helpers import minimal_worker_config


def minimal_runtime_config(**kwargs: object) -> AppConfig:
    return minimal_worker_config(**kwargs)  # type: ignore[arg-type]
