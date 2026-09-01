"""Shared contract-test fixtures for runtime module (RT-018, LLD §21.3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from runtime import API_ENTRY

from .helpers import FakeWorkerLoop, FakeWorkflowEngine, minimal_runtime_config


@pytest.fixture
def runtime_config() -> Any:
    return minimal_runtime_config()


@pytest.fixture
def bootstrap_for_tests() -> Callable[..., Any]:
    """Internal bootstrap helper seam (LLD §21.3 allowlist)."""

    def _factory(**kwargs: Any) -> Any:
        from runtime.composition import _bootstrap_for_tests

        return _bootstrap_for_tests(
            entry=kwargs.get("entry", API_ENTRY),
            config=kwargs.get("config", minimal_runtime_config()),
            persistence=kwargs.get("persistence"),
            task_queue=kwargs.get("task_queue"),
            workflow_engine=kwargs.get("workflow_engine"),
            worker_loop=kwargs.get("worker_loop"),
            call_order=kwargs.get("call_order"),
            persistence_error=kwargs.get("persistence_error"),
            telemetry=kwargs.get("telemetry"),
        )

    return _factory


@pytest.fixture
def fake_workflow_engine() -> FakeWorkflowEngine:
    return FakeWorkflowEngine()


@pytest.fixture
def fake_worker_loop() -> FakeWorkerLoop:
    return FakeWorkerLoop()
