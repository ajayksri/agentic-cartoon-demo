"""Client-side token-bucket rate limiting."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Client-side rate limiting — token-bucket throttling
# protects external LLM APIs from burst traffic when many workers run concurrently.
# GUARDRAIL: Capacity — throttle outbound LLM calls to stay within provider limits.

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from config.types import ProviderId

from .errors import ProviderRateLimitError
from .messages import client_rate_limit_message


class ClientRateLimiter:
    def __init__(
        self,
        *,
        rate_limit_per_minute: int | None,
        provider_id: ProviderId | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._disabled = rate_limit_per_minute is None or rate_limit_per_minute <= 0
        if self._disabled:
            self._capacity = 0.0
            self._refill_rate = 0.0
            self._tokens = 0.0
            self._t_last = self._clock()
        else:
            self._capacity = float(rate_limit_per_minute)
            self._refill_rate = self._capacity / 60.0
            self._tokens = self._capacity
            self._t_last = self._clock()

    def acquire(self) -> None:
        if self._disabled:
            return

        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._t_last)
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._t_last = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

        provider_id = self._provider_id or ProviderId.FAKE
        raise ProviderRateLimitError(
            client_rate_limit_message(provider_id=provider_id),
            provider_id=provider_id,
        )
