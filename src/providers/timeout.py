"""Timeout budget resolution and deadline guards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from config.types import ProviderId, TimeoutConfig

from .errors import ProviderTimeoutError


@dataclass(frozen=True, slots=True)
class TimeoutBudget:
    connect_seconds: float | None
    read_seconds: float
    total_seconds: float | None
    overall_deadline_seconds: float


class TimeoutContext:
    def __init__(
        self,
        *,
        timeout_config: TimeoutConfig,
        provider_id: ProviderId | None = None,
        error_mapper: object | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._timeout_config = timeout_config
        self._provider_id = provider_id
        self._error_mapper = error_mapper
        self._clock = clock or time.monotonic
        self._budget = self.resolve_budget(timeout_config)
        self._deadline: float = 0.0

    @classmethod
    def resolve_budget(cls, timeout_config: TimeoutConfig) -> TimeoutBudget:
        read = timeout_config.read_seconds

        if timeout_config.total_seconds is not None:
            total = timeout_config.total_seconds
            connect = timeout_config.connect_seconds
            if connect is not None:
                connect = min(connect, total)
            read = min(read, total)
            overall = total
        else:
            total = None
            connect = timeout_config.connect_seconds
            overall = read if connect is None else connect + read

        return TimeoutBudget(
            connect_seconds=connect,
            read_seconds=read,
            total_seconds=total,
            overall_deadline_seconds=overall,
        )

    def __enter__(self) -> TimeoutContext:
        self._deadline = self._clock() + self._budget.overall_deadline_seconds
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None

    def check_deadline(self) -> None:
        if self._clock() >= self._deadline:
            if self._provider_id is not None and self._error_mapper is not None:
                raise self._error_mapper.map_timeout(provider_id=self._provider_id)
            raise ProviderTimeoutError("deadline exceeded")

    def elapsed_violation(self) -> bool:
        return self._clock() >= self._deadline

    @property
    def budget(self) -> TimeoutBudget:
        return self._budget
