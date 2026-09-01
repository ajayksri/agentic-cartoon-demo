"""Internal observability configuration parsing (not exported from __init__.py)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import get_args

from .types import LogLevel

_VALID_LOG_LEVELS = frozenset(get_args(LogLevel))


@dataclass(frozen=True, slots=True)
class _ExportEndpoints:
    traces: str | None = None
    metrics: str | None = None


@dataclass(frozen=True, slots=True)
class _ObservabilityConfig:
    service_name: str
    log_level: LogLevel
    metric_name_adapter: Callable[[str], str] | None = None
    export_endpoints: _ExportEndpoints | None = None
    strict_telemetry_errors: bool = False


def _require_attr(settings: object, name: str) -> object:
    if not hasattr(settings, name):
        raise ValueError(f"missing required settings attribute: {name}")
    return getattr(settings, name)


def _parse_service_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("service_name must be a non-empty str")
    return value


def _parse_log_level(value: object) -> LogLevel:
    if value not in _VALID_LOG_LEVELS:
        raise ValueError(f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}")
    return value  # type: ignore[return-value]


def _parse_metric_name_adapter(value: object) -> Callable[[str], str] | None:
    if value is None:
        return None
    if not callable(value):
        raise ValueError("metric_name_adapter must be callable")
    return value


def _parse_export_endpoints(value: object) -> _ExportEndpoints | None:
    if value is None:
        return None
    traces: str | None = None
    metrics: str | None = None
    if hasattr(value, "traces"):
        traces_attr = getattr(value, "traces")
        if traces_attr is not None and not isinstance(traces_attr, str):
            raise ValueError("export_endpoints.traces must be a str or None")
        traces = traces_attr
    if hasattr(value, "metrics"):
        metrics_attr = getattr(value, "metrics")
        if metrics_attr is not None and not isinstance(metrics_attr, str):
            raise ValueError("export_endpoints.metrics must be a str or None")
        metrics = metrics_attr
    return _ExportEndpoints(traces=traces, metrics=metrics)


def _parse_strict_telemetry_errors(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("strict_telemetry_errors must be a bool")
    return value


def parse_settings(settings: object) -> _ObservabilityConfig:
    """Duck-type an opaque settings object into internal config."""
    service_name = _parse_service_name(_require_attr(settings, "service_name"))
    log_level = _parse_log_level(_require_attr(settings, "log_level"))

    metric_name_adapter: Callable[[str], str] | None = None
    if hasattr(settings, "metric_name_adapter"):
        metric_name_adapter = _parse_metric_name_adapter(
            getattr(settings, "metric_name_adapter")
        )

    export_endpoints: _ExportEndpoints | None = None
    if hasattr(settings, "export_endpoints"):
        export_endpoints = _parse_export_endpoints(getattr(settings, "export_endpoints"))

    strict_telemetry_errors = False
    if hasattr(settings, "strict_telemetry_errors"):
        strict_telemetry_errors = _parse_strict_telemetry_errors(
            getattr(settings, "strict_telemetry_errors")
        )

    return _ObservabilityConfig(
        service_name=service_name,
        log_level=log_level,
        metric_name_adapter=metric_name_adapter,
        export_endpoints=export_endpoints,
        strict_telemetry_errors=strict_telemetry_errors,
    )
