"""Shared contract-test fixtures for config module (CFG-011, LLD §10.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from .helpers import (
    minimal_valid_config,
    seed_credentials,
    write_config,
)


@pytest.fixture
def minimal_valid_config_fixture() -> dict[str, Any]:
    return minimal_valid_config()


@pytest.fixture
def write_config_fixture() -> Callable[[Path, dict[str, Any] | str], Any]:
    return write_config


@pytest.fixture
def seed_credentials_fixture() -> Callable[[pytest.MonkeyPatch], None]:
    return seed_credentials


@pytest.fixture
def prompt_files(tmp_path: Path) -> dict[str, Path]:
    """Create dummy prompt files referenced by minimal_valid_config."""
    paths: dict[str, Path] = {}
    for rel in (
        "prompts/topic_selector.txt",
        "prompts/scenario_generator.txt",
        "prompts/critic.txt",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"prompt for {rel}\n", encoding="utf-8")
        paths[rel] = target
    return paths
