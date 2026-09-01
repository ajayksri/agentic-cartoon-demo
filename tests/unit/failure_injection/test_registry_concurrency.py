"""Pre-code test mold for FINJ-002 — concurrent invoke_if_active smoke."""

from __future__ import annotations

import threading
from typing import cast

import pytest

from config.types import AppConfig, InjectionId
from tests.support.failure_injection_fixtures import stub_app_config


def test_concurrent_invoke_if_active_smoke() -> None:
    """Concurrent invoke_if_active from multiple threads does not deadlock or corrupt state."""
    from failure_injection.fakes import RecordingHook
    from failure_injection.registry import DefaultFailureInjectionRegistry

    config = cast(
        AppConfig,
        stub_app_config(enabled=True, active=frozenset({InjectionId.FINJ_Q_SLOW})),
    )
    registry = DefaultFailureInjectionRegistry(config)
    hook = RecordingHook()
    registry.register_hook(InjectionId.FINJ_Q_SLOW, hook)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(20):
                registry.invoke_if_active(InjectionId.FINJ_Q_SLOW)
        except BaseException as exc:  # noqa: BLE001 — capture thread failures
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    assert errors == []
    assert len(hook.calls) == 80
