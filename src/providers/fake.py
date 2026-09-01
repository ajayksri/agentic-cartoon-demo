"""Fake provider for tests and local development."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from config.types import ProviderConfig, ProviderId, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry

from .base import BaseRemoteProvider
from .constants import (
    FAKE_AGENT_CRITIC_PASS_DEFAULT,
    FAKE_AGENT_SCENARIO_DEFAULT,
    FAKE_AGENT_TOPIC_DEFAULT,
    FAKE_DEFAULT_CONTENT,
    FAKE_MIN_LATENCY_MS,
)
from .errors import ProviderError
from .types import GenerateRequest, GenerateResponse
from .internal_types import VendorCallResult
from .timeout import TimeoutBudget


def _default_content_for_request(request: GenerateRequest) -> str:
    """Return schema-valid agent stubs when messages match stage payloads (PD-001 demo path)."""
    for message in reversed(request.messages):
        text = message.content.strip()
        if not text or text[0] not in "[{":
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            if "source_id" in payload[0]:
                return FAKE_AGENT_TOPIC_DEFAULT
        if isinstance(payload, dict):
            if "scenario" in payload and "revision_number" in payload:
                return FAKE_AGENT_CRITIC_PASS_DEFAULT
            if "selected_topic" in payload and "cartoon_angle" in payload:
                return FAKE_AGENT_SCENARIO_DEFAULT
    return FAKE_DEFAULT_CONTENT


class FakeProgramMode(StrEnum):
    DEFAULT = "default"
    NEXT_RESPONSE = "next_response"
    NEXT_ERROR = "next_error"


@dataclass
class FakeProgramState:
    mode: FakeProgramMode = FakeProgramMode.DEFAULT
    next_response: GenerateResponse | None = None
    next_error: ProviderError | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class FakeVendorTransport:
    def __init__(
        self,
        *,
        state: FakeProgramState,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state = state
        self._clock = clock or time.monotonic

    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: TimeoutBudget,
    ) -> VendorCallResult:
        with self._state.lock:
            if self._state.mode is FakeProgramMode.NEXT_RESPONSE:
                programmed = self._state.next_response
                self._state.next_response = None
                self._state.next_error = None
                self._state.mode = FakeProgramMode.DEFAULT
                if programmed is None:
                    raise RuntimeError("programmed response missing")
                return VendorCallResult(
                    content=programmed.content,
                    model=programmed.model,
                    token_usage=programmed.token_usage,
                )

            if self._state.mode is FakeProgramMode.NEXT_ERROR:
                programmed_error = self._state.next_error
                self._state.next_error = None
                self._state.next_response = None
                self._state.mode = FakeProgramMode.DEFAULT
                if programmed_error is None:
                    raise RuntimeError("programmed error missing")
                raise programmed_error

        time.sleep(FAKE_MIN_LATENCY_MS / 1000.0)
        return VendorCallResult(
            content=_default_content_for_request(request),
            model=request.model,
            token_usage=None,
        )


class FakeProvider(BaseRemoteProvider):
    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        timeout_config: TimeoutConfig,
        registry: FailureInjectionRegistry | None = None,
        state: FakeProgramState | None = None,
        **base_kwargs: object,
    ) -> None:
        self._state = state or FakeProgramState()
        transport = FakeVendorTransport(state=self._state)
        super().__init__(
            provider_id=ProviderId.FAKE,
            provider_config=provider_config,
            timeout_config=timeout_config,
            registry=registry,
            transport=transport,
            **base_kwargs,  # type: ignore[arg-type]
        )

    def set_next_response(self, response: GenerateResponse) -> None:
        with self._state.lock:
            self._state.next_response = response
            self._state.next_error = None
            self._state.mode = FakeProgramMode.NEXT_RESPONSE

    def set_next_error(self, error: ProviderError) -> None:
        with self._state.lock:
            self._state.next_error = error
            self._state.next_response = None
            self._state.mode = FakeProgramMode.NEXT_ERROR

    def reset(self) -> None:
        with self._state.lock:
            self._state.mode = FakeProgramMode.DEFAULT
            self._state.next_response = None
            self._state.next_error = None

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        programmed: GenerateResponse | None
        with self._state.lock:
            programmed = (
                self._state.next_response
                if self._state.mode is FakeProgramMode.NEXT_RESPONSE
                else None
            )

        response = super().generate(request)

        if programmed is not None:
            from dataclasses import replace

            return replace(
                response,
                latency_ms=programmed.latency_ms,
                estimated_cost_usd=programmed.estimated_cost_usd,
            )
        return response
