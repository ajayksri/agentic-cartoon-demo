"""Unit-test doubles for failure_injection (not exported)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import InjectionContext


@dataclass
class RecordingHook:
    """Hook that records invocations and optionally raises. Unit tests only."""

    calls: list[InjectionContext | None] = field(default_factory=list)
    raise_on_invoke: BaseException | None = None

    def invoke(self, context: InjectionContext | None = None) -> None:
        self.calls.append(context)
        if self.raise_on_invoke is not None:
            raise self.raise_on_invoke
