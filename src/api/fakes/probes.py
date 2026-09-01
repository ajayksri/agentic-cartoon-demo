"""Fake readiness probe for contract tests."""

from __future__ import annotations

from api.types import DependencyCheck, DependencyCheckStatus


class FakeReadinessProbe:
    """Returns controlled DependencyCheck; check() never raises."""

    name: str

    def __init__(self, name: str, *, ok: bool = True, detail: str | None = None) -> None:
        self.name = name
        self._ok = ok
        self._detail = detail

    def check(self) -> DependencyCheck:
        return DependencyCheck(
            name=self.name,
            status=DependencyCheckStatus.OK if self._ok else DependencyCheckStatus.FAIL,
            detail=self._detail,
        )
