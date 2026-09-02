"""Shared pytest hooks for pre-code test molds."""

from __future__ import annotations

import pytest

from config.loader import CONFIG_PATH_ENV_VAR


@pytest.fixture(autouse=True)
def _isolate_operator_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent sourced local .env from breaking CLI contract tests.

    ``initiate`` bootstraps from ``CARTOON_CONFIG_PATH`` when set; operator shells
    often point at ``config/cartoon.yaml`` which is not present in CI/clean trees.
    """
    monkeypatch.delenv(CONFIG_PATH_ENV_VAR, raising=False)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Treat @pytest.mark.expect_fail as xfail until implementation lands."""
    for item in items:
        marker = item.get_closest_marker("expect_fail")
        if marker is None:
            continue
        reason = marker.kwargs.get("reason")
        if reason is None and marker.args:
            reason = marker.args[0]
        if reason is None:
            reason = "not implemented"
        item.add_marker(pytest.mark.xfail(reason=reason, strict=False))
