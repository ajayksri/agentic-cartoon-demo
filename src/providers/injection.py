"""Failure-injection gate for provider generate calls."""

from __future__ import annotations

from collections.abc import Sequence

from config.types import InjectionId
from failure_injection.protocols import FailureInjectionRegistry
from failure_injection.types import InjectionContext

from .constants import FINJ_PROVIDER_ORDER
from .types import GenerateRequest


class InjectionGate:
    def __init__(
        self,
        *,
        registry: FailureInjectionRegistry | None,
        order: Sequence[InjectionId] = FINJ_PROVIDER_ORDER,
    ) -> None:
        self._registry = registry
        self._order = order

    def evaluate(self, request: GenerateRequest) -> None:
        if self._registry is None:
            return

        context = InjectionContext(
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            task_attempt=request.task_attempt,
            metadata={},
        )

        for injection_id in self._order:
            self._registry.invoke_if_active(injection_id, context=context)
