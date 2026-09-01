"""Bootstrap and observability spies for runtime contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from config.types import AppConfig

from runtime.types import BootstrapResult, ProcessEntryPoint, WiredDependencies


@dataclass
class RecordingCallOrder:
    """Records ordered bootstrap steps for RT-TC-005."""

    calls: list[str] = field(default_factory=list)

    def record(self, name: str) -> None:
        self.calls.append(name)


@dataclass
class FakeCompositionRoot:
    """Records bootstrap order without production wiring."""

    config: AppConfig
    call_order: RecordingCallOrder = field(default_factory=RecordingCallOrder)
    _wired: WiredDependencies | None = None

    def bootstrap(
        self,
        entry: ProcessEntryPoint,
        *,
        worker_config: object | None = None,
    ) -> BootstrapResult:
        del worker_config
        self.call_order.record(f"bootstrap:{entry.kind.value}")
        self._wired = WiredDependencies(entry=entry, config=self.config)
        return BootstrapResult(
            entry=entry,
            config_loaded=True,
            observability_configured=True,
            failure_injection_configured=True,
        )

    def wired_dependencies(self) -> WiredDependencies:
        if self._wired is None:
            raise RuntimeError("bootstrap not called")
        return self._wired
