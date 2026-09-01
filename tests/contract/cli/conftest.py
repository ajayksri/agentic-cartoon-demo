"""Shared contract-test fixtures for cli module (CLI-023, LLD §14)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from .helpers import build_cli_dependencies, load_fakes, minimal_client_config


@pytest.fixture
def cli_app_under_test(recording_cli_telemetry) -> Callable[..., Any]:
    """Build wired CliApp with injectable FakeApiClient (LLD §14)."""

    def _factory(*, api_client: Any | None = None) -> Any:
        from cli import create_cli_app

        client_cls, logger_cls = load_fakes()
        resolved_client = api_client or client_cls()
        deps = build_cli_dependencies(
            logger=logger_cls(),
            telemetry=recording_cli_telemetry,
        )
        return create_cli_app(
            deps=deps,
            api_client=resolved_client,
            telemetry=recording_cli_telemetry,
        )

    return _factory


@pytest.fixture
def fake_api_client() -> Any:
    """Fresh FakeApiClient instance."""
    client_cls, _logger_cls = load_fakes()
    return client_cls()


@pytest.fixture
def recording_logger() -> Any:
    """RecordingLogger seam for log assertions (LLD §14 allowlist)."""
    _client_cls, logger_cls = load_fakes()
    logger = logger_cls()
    if hasattr(logger, "clear"):
        logger.clear()
    return logger


@pytest.fixture
def recording_cli_telemetry() -> Any:
    """RecordingCliTelemetry seam for event assertions (LLD §12.1 allowlist)."""
    from cli.telemetry import RecordingCliTelemetry

    telemetry = RecordingCliTelemetry()
    telemetry.clear()
    return telemetry


@pytest.fixture
def cli_client_config() -> Any:
    return minimal_client_config()
