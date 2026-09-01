"""Public value and error types for the failure_injection module contract boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from config.types import InjectionId


@dataclass(frozen=True, slots=True)
class InjectionContext:
    """Optional correlation and metadata passed to hooks at invocation."""

    workflow_id: str | None = None
    task_id: str | None = None
    task_attempt: int | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


class FailureInjectionError(Exception):
    """Base class for failure injection registry errors."""

    code: str


class RegistryNotConfiguredError(FailureInjectionError):
    """Raised when accessors are called before configure_failure_injection (FINJ-E001)."""

    code = "FINJ-E001"


class DuplicateHookError(FailureInjectionError):
    """Raised when register_hook is called for an already-registered injection ID (FINJ-E002)."""

    code = "FINJ-E002"

    def __init__(self, injection_id: InjectionId) -> None:
        self.injection_id = injection_id
        super().__init__(f"Hook already registered for injection ID {injection_id.value}")


class HookNotRegisteredError(FailureInjectionError):
    """Raised when an active injection ID has no registered hook (FINJ-E003)."""

    code = "FINJ-E003"

    def __init__(self, injection_id: InjectionId) -> None:
        self.injection_id = injection_id
        super().__init__(f"No hook registered for active injection ID {injection_id.value}")


class InjectionInvocationError(FailureInjectionError):
    """Raised when hook invoke fails unexpectedly (FINJ-E004)."""

    code = "FINJ-E004"

    def __init__(
        self,
        injection_id: InjectionId,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.injection_id = injection_id
        self.cause = cause
        message = f"Hook invocation failed for injection ID {injection_id.value}"
        super().__init__(message)
