"""Pre-code test mold for PRV-013 — FakeProvider state machine (LLD §4.12, §11)."""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from config.types import ProviderId
from providers import (
    GenerateRequest,
    GenerateResponse,
    ProviderMessage,
    ProviderMessageRole,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TokenUsage,
)

def _valid_request(*, model: str = "fake-model") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=(ProviderMessage(role=ProviderMessageRole.USER, content="hello"),),
    )
def _programmed_response(*, content: str = "programmed") -> GenerateResponse:
    return GenerateResponse(
        content=content,
        model="fake-model",
        provider_id=ProviderId.FAKE,
        latency_ms=1.0,
        token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        estimated_cost_usd=Decimal("0.001"),
    )
def _build_fake_provider() -> object:
    from config.types import ProviderConfig, TimeoutConfig
    from providers.fake import FakeProvider

    return FakeProvider(
        provider_config=ProviderConfig(
            api_key_env="FAKE_API_KEY",
            rate_limit_per_minute=None,
            pricing=None,
        ),
        timeout_config=TimeoutConfig(
            connect_seconds=None,
            read_seconds=30.0,
            total_seconds=None,
        ),
    )
def test_set_next_response_consumed_once_then_default() -> None:
    """Programmed success is one-shot; second generate returns DEFAULT stub."""
    fake = _build_fake_provider()
    request = _valid_request()
    programmed = _programmed_response(content="once-only")

    fake.set_next_response(programmed)
    first = fake.generate(request)
    second = fake.generate(request)

    assert first.content == "once-only"
    assert second.content != "once-only"
def test_set_next_error_consumed_once_then_default() -> None:
    """Programmed error is one-shot; second generate succeeds with DEFAULT stub."""
    fake = _build_fake_provider()
    request = _valid_request()
    error = ProviderTimeoutError("simulated timeout", provider_id=ProviderId.FAKE)

    fake.set_next_error(error)
    with pytest.raises(ProviderTimeoutError):
        fake.generate(request)

    response = fake.generate(request)
    assert response.content
def test_reset_clears_programmed_error() -> None:
    """reset() after set_next_error restores default stub success."""
    fake = _build_fake_provider()
    request = _valid_request()

    fake.set_next_error(ProviderRateLimitError("rate limited", provider_id=ProviderId.FAKE))
    fake.reset()

    response = fake.generate(request)
    assert response.content
def test_set_next_response_clears_programmed_error() -> None:
    """set_next_response clears a previously programmed error (mutual exclusion)."""
    from providers.fake import FakeProgramMode, FakeProgramState

    state = FakeProgramState()
    fake = _build_fake_provider()
    fake._state = state  # type: ignore[attr-defined]

    fake.set_next_error(ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE))
    fake.set_next_response(_programmed_response())

    assert state.mode == FakeProgramMode.NEXT_RESPONSE
    assert state.next_error is None
def test_set_next_error_clears_programmed_response() -> None:
    """set_next_error clears a previously programmed response (mutual exclusion)."""
    from providers.fake import FakeProgramMode, FakeProgramState

    state = FakeProgramState()
    fake = _build_fake_provider()
    fake._state = state  # type: ignore[attr-defined]

    fake.set_next_response(_programmed_response())
    fake.set_next_error(ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE))

    assert state.mode == FakeProgramMode.NEXT_ERROR
    assert state.next_response is None
def test_sequential_errors_raise_matching_subclasses() -> None:
    """Sequential set_next_error calls yield distinct ProviderError subclasses (PRV-TC-032)."""
    from providers import ProviderAuthenticationError, ProviderSchemaValidationError

    fake = _build_fake_provider()
    request = _valid_request()
    sequence = (
        ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE),
        ProviderRateLimitError("rate", provider_id=ProviderId.FAKE),
        ProviderAuthenticationError("auth", provider_id=ProviderId.FAKE),
        ProviderSchemaValidationError("schema", provider_id=ProviderId.FAKE),
    )

    for expected in sequence:
        fake.set_next_error(expected)
        with pytest.raises(type(expected)):
            fake.generate(request)
def test_thread_safe_concurrent_state_mutations() -> None:
    """State mutations under lock remain consistent with concurrent programming."""
    fake = _build_fake_provider()
    request = _valid_request()
    barrier = threading.Barrier(4)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            if index % 2 == 0:
                fake.set_next_response(_programmed_response(content=f"worker-{index}"))
                fake.generate(request)
            else:
                fake.set_next_error(
                    ProviderTimeoutError(f"timeout-{index}", provider_id=ProviderId.FAKE)
                )
                with pytest.raises(ProviderTimeoutError):
                    fake.generate(request)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
def test_default_mode_returns_stub_content_with_latency() -> None:
    """DEFAULT mode sleeps FAKE_MIN_LATENCY_MS and returns stub VendorCallResult fields."""
    from providers.constants import FAKE_DEFAULT_CONTENT, FAKE_MIN_LATENCY_MS

    fake = _build_fake_provider()
    request = _valid_request(model="model-x")

    response = fake.generate(request)

    assert response.content == FAKE_DEFAULT_CONTENT
    assert response.model == "model-x"
    assert response.latency_ms >= FAKE_MIN_LATENCY_MS


def test_default_mode_returns_schema_valid_topic_stub() -> None:
    """DEFAULT mode returns topic-selection JSON when user payload is candidate list."""
    from providers.constants import FAKE_AGENT_TOPIC_DEFAULT

    fake = _build_fake_provider()
    request = GenerateRequest(
        model="fake-model",
        messages=(
            ProviderMessage(role=ProviderMessageRole.SYSTEM, content="system"),
            ProviderMessage(
                role=ProviderMessageRole.USER,
                content='[{"source_id":"hn-1","title":"Rust async"}]',
            ),
        ),
    )

    response = fake.generate(request)

    assert response.content == FAKE_AGENT_TOPIC_DEFAULT
