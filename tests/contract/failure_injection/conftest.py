"""Canonical contract fixtures for failure_injection (LLD §10.1, §10.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

import failure_injection


@dataclass
class InlineRecordingHook:
    """Contract-test Hook double; not imported from fakes.py."""

    calls: list[failure_injection.InjectionContext | None] = field(default_factory=list)
    raise_on_invoke: BaseException | None = None

    def invoke(self, context: failure_injection.InjectionContext | None = None) -> None:
        self.calls.append(context)
        if self.raise_on_invoke is not None:
            raise self.raise_on_invoke
