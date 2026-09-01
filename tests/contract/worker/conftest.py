"""Shared contract-test fixtures for worker module (WKR-017, LLD §12.1)."""

from __future__ import annotations

import pytest

from config.types import AppConfig

from .helpers import memory_worker_loop, minimal_worker_config


@pytest.fixture
def worker_config() -> AppConfig:
    return minimal_worker_config()


@pytest.fixture
def memory_worker(worker_config: AppConfig):
    return memory_worker_loop(config=worker_config)
