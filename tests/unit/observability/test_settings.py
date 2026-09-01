"""Unit tests for observability internal settings parsing (OBS-002)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import observability
from observability.settings import (
    _ExportEndpoints,
    _ObservabilityConfig,
    parse_settings,
)


def test_parse_settings_minimal_valid() -> None:
    settings = SimpleNamespace(service_name="cartoon-api", log_level="INFO")

    config = parse_settings(settings)

    assert config == _ObservabilityConfig(
        service_name="cartoon-api",
        log_level="INFO",
    )


def test_parse_settings_all_optional_fields() -> None:
    def adapt(name: str) -> str:
        return f"prefix.{name}"

    settings = SimpleNamespace(
        service_name="cartoon-worker",
        log_level="DEBUG",
        metric_name_adapter=adapt,
        export_endpoints=SimpleNamespace(
            traces="http://localhost:4317",
            metrics="http://localhost:4318",
        ),
        strict_telemetry_errors=True,
    )

    config = parse_settings(settings)

    assert config.service_name == "cartoon-worker"
    assert config.log_level == "DEBUG"
    assert config.metric_name_adapter is adapt
    assert config.export_endpoints == _ExportEndpoints(
        traces="http://localhost:4317",
        metrics="http://localhost:4318",
    )
    assert config.strict_telemetry_errors is True


def test_parse_settings_missing_service_name_raises() -> None:
    settings = SimpleNamespace(log_level="INFO")

    with pytest.raises(ValueError, match="service_name"):
        parse_settings(settings)


def test_parse_settings_missing_log_level_raises() -> None:
    settings = SimpleNamespace(service_name="cartoon-api")

    with pytest.raises(ValueError, match="log_level"):
        parse_settings(settings)


def test_parse_settings_empty_service_name_raises() -> None:
    settings = SimpleNamespace(service_name="", log_level="INFO")

    with pytest.raises(ValueError, match="service_name"):
        parse_settings(settings)


def test_parse_settings_invalid_log_level_raises() -> None:
    settings = SimpleNamespace(service_name="cartoon-api", log_level="TRACE")

    with pytest.raises(ValueError, match="log_level"):
        parse_settings(settings)


@pytest.mark.parametrize(
    ("endpoints", "expected"),
    [
        (None, None),
        (SimpleNamespace(), _ExportEndpoints()),
        (SimpleNamespace(traces="http://traces:4317"), _ExportEndpoints(traces="http://traces:4317")),
        (SimpleNamespace(metrics="http://metrics:4318"), _ExportEndpoints(metrics="http://metrics:4318")),
        (
            SimpleNamespace(traces="http://traces:4317", metrics="http://metrics:4318"),
            _ExportEndpoints(traces="http://traces:4317", metrics="http://metrics:4318"),
        ),
    ],
)
def test_parse_settings_export_endpoints_shapes(
    endpoints: object,
    expected: _ExportEndpoints | None,
) -> None:
    settings = SimpleNamespace(
        service_name="cartoon-api",
        log_level="WARNING",
        export_endpoints=endpoints,
    )

    config = parse_settings(settings)

    assert config.export_endpoints == expected


def test_parse_settings_strict_telemetry_errors_defaults_false() -> None:
    settings = SimpleNamespace(service_name="cartoon-api", log_level="ERROR")

    config = parse_settings(settings)

    assert config.strict_telemetry_errors is False


@pytest.mark.parametrize("strict_value", [True, False])
def test_parse_settings_strict_telemetry_errors_explicit(strict_value: bool) -> None:
    settings = SimpleNamespace(
        service_name="cartoon-api",
        log_level="ERROR",
        strict_telemetry_errors=strict_value,
    )

    config = parse_settings(settings)

    assert config.strict_telemetry_errors is strict_value


def test_settings_not_exported_from_public_init() -> None:
    assert "parse_settings" not in observability.__all__
    assert "_ObservabilityConfig" not in observability.__all__
    assert "_ExportEndpoints" not in observability.__all__
