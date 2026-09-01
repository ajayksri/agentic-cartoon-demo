"""Pre-code test mold for PRV-009 — ClientRateLimiter (LLD §4.5, §8)."""

from __future__ import annotations

import threading

import pytest

from config.types import ProviderId
from providers.errors import ProviderRateLimitError

def test_burst_allows_capacity_immediate_calls() -> None:
    """LLD §8 burst vector: C=60 immediate calls all pass."""
    from providers.rate_limit import ClientRateLimiter

    clock = {"now": 0.0}

    def fake_clock() -> float:
        return clock["now"]

    limiter = ClientRateLimiter(rate_limit_per_minute=60, clock=fake_clock)

    for _ in range(60):
        limiter.acquire()
def test_exhaust_raises_on_capacity_plus_one() -> None:
    """LLD §8 exhaust vector: 61st immediate call raises ProviderRateLimitError."""
    from providers.rate_limit import ClientRateLimiter

    clock = {"now": 0.0}
    limiter = ClientRateLimiter(rate_limit_per_minute=60, clock=lambda: clock["now"])

    for _ in range(60):
        limiter.acquire()

    with pytest.raises(ProviderRateLimitError) as exc_info:
        limiter.acquire()

    assert exc_info.value.code == "PRV_RATE"
    assert exc_info.value.retryable is True
def test_refill_allows_call_after_one_second() -> None:
    """LLD §8 refill vector: ~1 token/sec after exhausting bucket."""
    from providers.rate_limit import ClientRateLimiter

    clock = {"now": 0.0}
    limiter = ClientRateLimiter(rate_limit_per_minute=60, clock=lambda: clock["now"])

    for _ in range(60):
        limiter.acquire()

    clock["now"] = 1.0
    limiter.acquire()
def test_disabled_limit_is_no_op() -> None:
    """LLD §8 disabled vector: rate_limit_per_minute=None never raises."""
    from providers.rate_limit import ClientRateLimiter

    limiter = ClientRateLimiter(rate_limit_per_minute=None)

    for _ in range(200):
        limiter.acquire()


def test_zero_or_negative_limit_is_no_op() -> None:
    """LLD §8: misconfigured zero/negative limits treated as disabled no-op."""
    from providers.rate_limit import ClientRateLimiter

    for limit in (0, -1):
        limiter = ClientRateLimiter(rate_limit_per_minute=limit)
        for _ in range(200):
            limiter.acquire()
@pytest.mark.prv_tc("050")
def test_client_rate_limit_message_distinct_from_vendor_429() -> None:
    """Client-side exhaustion uses client_rate_limit_message template."""
    from providers.rate_limit import ClientRateLimiter

    clock = {"now": 0.0}
    limiter = ClientRateLimiter(rate_limit_per_minute=1, clock=lambda: clock["now"])
    limiter.acquire()

    with pytest.raises(ProviderRateLimitError) as exc_info:
        limiter.acquire()

    message = str(exc_info.value)
    assert "client rate limit exceeded" in message
    assert ProviderId.OPENAI.value in message or "provider=" in message
def test_acquire_is_thread_safe_smoke() -> None:
    """Token bucket uses threading.Lock for concurrent acquire calls."""
    from providers.rate_limit import ClientRateLimiter

    limiter = ClientRateLimiter(rate_limit_per_minute=120)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(10):
                limiter.acquire()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
