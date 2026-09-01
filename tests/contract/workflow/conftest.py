"""Shared contract-test fixtures for workflow module (WF-014, LLD §14)."""

from __future__ import annotations

import pytest

from config import AppConfig

from .helpers import memory_workflow_engine, minimal_workflow_config


@pytest.fixture
def minimal_workflow_config_fixture() -> AppConfig:
    return minimal_workflow_config()


@pytest.fixture
def memory_workflow_engine_fixture() -> tuple[object, object]:
    engine, txn = memory_workflow_engine()
    return engine, txn
