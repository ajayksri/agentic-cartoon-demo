"""Pre-code test mold for PRV-008 — TimeoutContext (LLD §4.6, §9.1)."""

from __future__ import annotations

import pytest

from config.types import ProviderId, TimeoutConfig
from providers.errors import ProviderTimeoutError

@pytest.mark.parametrize(
    ("connect", "read", "total", "expected_connect", "expected_read", "expected_overall"),
    [
        (10.0, 20.0, 30.0, 10.0, 20.0, 30.0),
        (10.0, 20.0, 15.0, 10.0, 15.0, 15.0),
        (None, 30.0, None, None, 30.0, 30.0),
        (5.0, 20.0, None, 5.0, 20.0, 25.0),
    ],
    ids=["total_caps_sub_budgets", "total_tightens_read", "read_only", "connect_plus_read"],
)
def test_resolve_budget_precedence_vectors(
    connect: float | None,
    read: float,
    total: float | None,
    expected_connect: float | None,
    expected_read: float,
    expected_overall: float,
) -> None:
    """CG-PRV-002 precedence table from LLD §9.1."""
    from providers.timeout import TimeoutContext

    config = TimeoutConfig(connect_seconds=connect, read_seconds=read, total_seconds=total)
    budget = TimeoutContext.resolve_budget(config)

    assert budget.connect_seconds == expected_connect
    assert budget.read_seconds == expected_read
    assert budget.total_seconds == total
    assert budget.overall_deadline_seconds == expected_overall
@pytest.mark.prv_tc("020")
def test_check_deadline_raises_provider_timeout_error() -> None:
    """Deadline guard raises ProviderTimeoutError with PRV_TIMEOUT, retryable=True."""
    from providers.error_mapper import VendorErrorMapper
    from providers.timeout import TimeoutBudget, TimeoutContext

    clock = {"now": 0.0}

    def fake_clock() -> float:
        return clock["now"]

    budget = TimeoutBudget(
        connect_seconds=None,
        read_seconds=0.01,
        total_seconds=None,
        overall_deadline_seconds=0.01,
    )
    mapper = VendorErrorMapper(provider_id=ProviderId.OPENAI)
    ctx = TimeoutContext(
        timeout_config=TimeoutConfig(None, 0.01, None),
        provider_id=ProviderId.OPENAI,
        error_mapper=mapper,
        clock=fake_clock,
    )
    ctx._budget = budget  # type: ignore[attr-defined]
    ctx._deadline = fake_clock() + budget.overall_deadline_seconds

    clock["now"] = 1.0

    with pytest.raises(ProviderTimeoutError) as exc_info:
        ctx.check_deadline()

    assert exc_info.value.code == "PRV_TIMEOUT"
    assert exc_info.value.retryable is True
def test_elapsed_violation_reports_deadline_exceeded() -> None:
    from providers.timeout import TimeoutBudget, TimeoutContext

    clock = {"now": 0.0}

    def fake_clock() -> float:
        return clock["now"]

    ctx = TimeoutContext(
        timeout_config=TimeoutConfig(None, 1.0, None),
        clock=fake_clock,
    )
    ctx._budget = TimeoutBudget(None, 1.0, None, 1.0)  # type: ignore[attr-defined]
    ctx._deadline = 1.0

    assert ctx.elapsed_violation() is False
    clock["now"] = 2.0
    assert ctx.elapsed_violation() is True
