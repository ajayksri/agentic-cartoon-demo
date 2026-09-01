"""Unit tests for runtime.settings (RT-001)."""

from __future__ import annotations

from runtime import API_ENTRY, COORDINATOR_ENTRY
from runtime.constants import DEFAULT_API_HOST, DEFAULT_API_PORT, DEFAULT_WORKER_ROLE
from runtime.settings import ApiServerConfig, WorkerProcessConfig, build_observability_settings

from tests.unit.runtime.helpers import minimal_runtime_config


def test_build_observability_settings_maps_service_name() -> None:
    settings = build_observability_settings(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
    )
    assert settings.service_name == "cartoon-demo-api"
    assert settings.log_level == "INFO"
    assert settings.export_endpoints is None


def test_build_observability_settings_uses_entry_service_name() -> None:
    settings = build_observability_settings(
        entry=COORDINATOR_ENTRY,
        config=minimal_runtime_config(),
    )
    assert settings.service_name == "cartoon-demo-coordinator"


def test_api_server_config_defaults() -> None:
    config = ApiServerConfig()
    assert config.host == DEFAULT_API_HOST
    assert config.port == DEFAULT_API_PORT


def test_worker_process_config_default_role() -> None:
    config = WorkerProcessConfig()
    assert config.worker_role is DEFAULT_WORKER_ROLE
    assert config.loop_config_overrides is None
