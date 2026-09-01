"""Public runtime error types."""

from __future__ import annotations

from .types import ProcessEntryPoint, ProcessKind


class RuntimeModuleError(Exception):
    """Base class for runtime module errors."""

    code: str = "RT_ERROR"


class BootstrapError(RuntimeModuleError):
    """Wiring failure during process bootstrap."""

    code = "RT_BOOTSTRAP"

    def __init__(
        self,
        message: str,
        *,
        entry: ProcessEntryPoint | None = None,
    ) -> None:
        super().__init__(message)
        self.entry = entry


class ProcessStartupError(RuntimeModuleError):
    """Entry runner failed before domain loops started."""

    code = "RT_STARTUP"

    def __init__(self, message: str, *, entry: ProcessEntryPoint) -> None:
        super().__init__(message)
        self.entry = entry


class DependencyWiringError(RuntimeModuleError):
    """Missing or invalid collaborator for the active process entry."""

    code = "RT_WIRING"

    def __init__(
        self,
        message: str,
        *,
        entry: ProcessEntryPoint,
        dependency: str,
    ) -> None:
        super().__init__(message)
        self.entry = entry
        self.dependency = dependency


class ProcessShutdownError(RuntimeModuleError):
    """Graceful shutdown exceeded grace period or failed."""

    code = "RT_SHUTDOWN"

    def __init__(self, message: str, *, entry: ProcessEntryPoint) -> None:
        super().__init__(message)
        self.entry = entry


class UnsupportedProcessKindError(RuntimeModuleError):
    """Bootstrap attempted for an unsupported process kind."""

    code = "RT_UNSUPPORTED_KIND"

    def __init__(self, message: str, *, kind: ProcessKind) -> None:
        super().__init__(message)
        self.kind = kind
