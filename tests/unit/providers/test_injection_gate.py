"""Pre-code test mold for PRV-010 — InjectionGate (LLD §4.4, §10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest

from config.types import InjectionId
from failure_injection.types import InjectionContext
from providers.errors import ProviderRateLimitError, ProviderTimeoutError
from providers.types import GenerateRequest, ProviderMessage, ProviderMessageRole

def _request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-4o-mini",
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hi"),),
        workflow_id="wf-1",
        task_id="task-1",
        task_attempt=2,
    )
@dataclass
class _StubRegistry:
    calls: list[tuple[InjectionId, InjectionContext]] = field(default_factory=list)
    active: set[InjectionId] = field(default_factory=set)
    raises_on: InjectionId | None = None
    raise_error: BaseException | None = None

    def invoke_if_active(self, injection_id: InjectionId, *, context: InjectionContext) -> bool:
        self.calls.append((injection_id, context))
        if injection_id in self.active:
            if self.raises_on is injection_id and self.raise_error is not None:
                raise self.raise_error
            return True
        return False
def test_none_registry_is_no_op() -> None:
    from providers.injection import InjectionGate

    gate = InjectionGate(registry=None)
    gate.evaluate(_request())
def test_evaluation_order_matches_finj_provider_order() -> None:
    from providers.constants import FINJ_PROVIDER_ORDER
    from providers.injection import InjectionGate

    registry = _StubRegistry()
    gate = InjectionGate(registry=cast(object, registry))

    gate.evaluate(_request())

    assert [call[0] for call in registry.calls] == list(FINJ_PROVIDER_ORDER)
def test_injection_context_populated_from_request_fields() -> None:
    from providers.injection import InjectionGate

    registry = _StubRegistry()
    gate = InjectionGate(registry=cast(object, registry))

    gate.evaluate(_request())

    _, context = registry.calls[0]
    assert context.workflow_id == "wf-1"
    assert context.task_id == "task-1"
    assert context.task_attempt == 2
    assert context.metadata == {}
def test_short_circuits_on_first_active_hook_raise() -> None:
    from providers.injection import InjectionGate

    registry = _StubRegistry(
        active={InjectionId.FINJ_PRV_TIMEOUT},
        raises_on=InjectionId.FINJ_PRV_TIMEOUT,
        raise_error=ProviderTimeoutError("finj timeout"),
    )
    gate = InjectionGate(registry=cast(object, registry))

    with pytest.raises(ProviderTimeoutError):
        gate.evaluate(_request())

    assert len(registry.calls) == 1
    assert registry.calls[0][0] is InjectionId.FINJ_PRV_TIMEOUT
def test_later_finj_ids_skipped_after_short_circuit() -> None:
    from providers.injection import InjectionGate

    registry = _StubRegistry(
        active={InjectionId.FINJ_PRV_RATE},
        raises_on=InjectionId.FINJ_PRV_RATE,
        raise_error=ProviderRateLimitError("finj rate"),
    )
    gate = InjectionGate(registry=cast(object, registry))

    with pytest.raises(ProviderRateLimitError):
        gate.evaluate(_request())

    assert all(call[0] != InjectionId.FINJ_PRV_INVALID for call in registry.calls)
