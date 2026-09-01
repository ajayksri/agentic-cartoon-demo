"""Shared contract-test fixtures for collector module (COL-012, LLD §10.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import AppConfig

from .helpers import fixtures_dir, minimal_collection_config


@pytest.fixture
def minimal_collection_config_fixture() -> AppConfig:
    return minimal_collection_config()


@pytest.fixture
def collector_fixtures_dir() -> Path:
    return fixtures_dir()
