"""Runtime process settings builders (internal)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from config.types import AppConfig, TaskType
from observability.types import LogLevel

from .constants import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_HTTP_SHUTDOWN_GRACE_SECONDS,
    DEFAULT_WORKER_ROLE,
)

if TYPE_CHECKING:
    from worker.types import WorkerLoopConfig

    from .types import ProcessEntryPoint


@dataclass(frozen=True, slots=True)
class RuntimeObservabilitySettings:
    """Observability bootstrap settings for a process entry (CG-RT-004)."""

    service_name: str
    log_level: LogLevel
    metric_name_adapter: Callable[[str], str] | None = None
    export_endpoints: object | None = None
    strict_telemetry_errors: bool = False


@dataclass(frozen=True, slots=True)
class ApiServerConfig:
    """HTTP host tuning for the API process."""

    host: str = DEFAULT_API_HOST
    port: int = DEFAULT_API_PORT
    graceful_shutdown_seconds: float = DEFAULT_HTTP_SHUTDOWN_GRACE_SECONDS


@dataclass(frozen=True, slots=True)
class WorkerProcessConfig:
    """Worker entry configuration carrier (M1 extension — LLD §4.3)."""

    worker_role: TaskType = DEFAULT_WORKER_ROLE
    loop_config_overrides: WorkerLoopConfig | None = None


def build_observability_settings(
    *,
    entry: ProcessEntryPoint,
    config: AppConfig,
    strict_telemetry_errors: bool = False,
) -> RuntimeObservabilitySettings:
    """Map process entry and config to observability bootstrap settings."""
    del config  # log_level from AppConfig deferred until CG-RT-HLD-005
    log_level: LogLevel = "INFO"
    return RuntimeObservabilitySettings(
        service_name=entry.service_name,
        log_level=log_level,
        export_endpoints=None,
        strict_telemetry_errors=strict_telemetry_errors,
    )
