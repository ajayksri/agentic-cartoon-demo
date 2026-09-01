"""Contract tests PRV-TC-001 through PRV-TC-070 (PRV-018).

Imports ONLY from the providers package public surface (`providers.__init__`).
Boundary imports for stub injection live in helpers.py / conftest.py per LLD §7.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from config.types import InjectionId, ProviderId
from providers import (
    FakeProvider,
    GenerateRequest,
    GenerateResponse,
    ModelProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderErrorClass,
    ProviderMessage,
    ProviderMessageRole,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderSchemaValidationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnknownError,
    TokenUsage,
    create_provider,
    default_retryable,
)

from .helpers import (
    build_finj_registry,
    create_fake_provider,
    generate_with_recording_telemetry,
    generate_with_stub_transport,
    make_stub_transport,
    minimal_provider_config,
    programmed_fake_response,
    recording_observability,
    setup_recording_provider,
    stub_failure_signal,
    stub_success_result,
    valid_generate_request,
)

@pytest.mark.prv_tc("001")
def test_prv_tc_001_create_provider_returns_model_provider_per_id(
    provider_env_keys: None,
) -> None:
    """PRV-TC-001: create_provider returns ModelProvider with matching provider_id."""
    config = minimal_provider_config()

    for provider_id in (
        ProviderId.OPENAI,
        ProviderId.ANTHROPIC,
        ProviderId.GEMINI,
        ProviderId.KIMI,
        ProviderId.FAKE,
    ):
        provider = create_provider(provider_id=provider_id, config=config)
        assert isinstance(provider, ModelProvider)
        assert provider.provider_id == provider_id
@pytest.mark.prv_tc("002")
def test_prv_tc_002_agent_provider_reassignment_same_interface(
    provider_env_keys: None,
) -> None:
    """PRV-TC-002: different providers accept identical GenerateRequest shape."""
    config = minimal_provider_config()
    request = valid_generate_request()
    openai_response = generate_with_stub_transport(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=make_stub_transport(result=stub_success_result()),
        request=request,
    )
    fake = create_provider(provider_id=ProviderId.FAKE, config=config)
    fake_response = fake.generate(request)

    assert isinstance(openai_response, GenerateResponse)
    assert isinstance(fake_response, GenerateResponse)
@pytest.mark.prv_tc("003")
def test_prv_tc_003_factory_resolves_credential_only_for_requested_provider() -> None:
    """PRV-TC-003: only requested provider env var is resolved."""
    from .helpers import CredentialResolveSpy

    spy = CredentialResolveSpy({"OPENAI_API_KEY": "openai-test-key"})
    config = minimal_provider_config(
        openai_only_agents=True,
        credential_resolver=spy,
    )

    create_provider(provider_id=ProviderId.OPENAI, config=config)

    assert spy.requests == ["OPENAI_API_KEY"]
@pytest.mark.prv_tc("004")
def test_prv_tc_004_generate_returns_typed_response(provider_env_keys: None) -> None:
    """PRV-TC-004: FakeProvider programmed success returns typed GenerateResponse."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    programmed = programmed_fake_response(content="typed response", latency_ms=3.0)
    fake.set_next_response(programmed)

    response = fake.generate(valid_generate_request())

    assert response.content == "typed response"
    assert response.model == programmed.model
    assert response.provider_id == ProviderId.FAKE
    assert response.latency_ms == 3.0
@pytest.mark.prv_tc("005")
def test_prv_tc_005_empty_messages_rejected(provider_env_keys: None) -> None:
    """PRV-TC-005: empty messages raises ValueError before provider invocation."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    request = GenerateRequest(model="fake-model", messages=())

    with pytest.raises(ValueError, match="messages"):
        fake.generate(request)
@pytest.mark.prv_tc("010")
def test_prv_tc_010_timeout_error_classification(provider_env_keys: None) -> None:
    """PRV-TC-010: programmed ProviderTimeoutError has timeout class and retryable=True."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    fake.set_next_error(
        ProviderTimeoutError("deadline exceeded", provider_id=ProviderId.FAKE),
    )

    with pytest.raises(ProviderTimeoutError) as exc_info:
        fake.generate(valid_generate_request())

    assert exc_info.value.code == "PRV_TIMEOUT"
    assert exc_info.value.error_class == ProviderErrorClass.TIMEOUT
    assert exc_info.value.retryable is True
@pytest.mark.prv_tc("011")
def test_prv_tc_011_rate_limit_error_classification(
    provider_env_keys: None,
) -> None:
    """PRV-TC-011: stub transport 429 signal raises ProviderRateLimitError."""
    config = minimal_provider_config()
    signal = stub_failure_signal(is_rate_limit=True, http_status=429)
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderRateLimitError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    assert exc_info.value.error_class == ProviderErrorClass.RATE_LIMIT
    assert exc_info.value.retryable is True
@pytest.mark.prv_tc("012")
def test_prv_tc_012_authentication_error_is_permanent(
    provider_env_keys: None,
) -> None:
    """PRV-TC-012: auth failure raises ProviderAuthenticationError retryable=False."""
    config = minimal_provider_config()
    signal = stub_failure_signal(is_auth_error=True, http_status=401)
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    assert exc_info.value.retryable is False
@pytest.mark.prv_tc("013")
def test_prv_tc_013_provider_unavailable_is_transient(
    provider_env_keys: None,
) -> None:
    """PRV-TC-013: 503 signal raises ProviderUnavailableError retryable=True."""
    config = minimal_provider_config()
    signal = stub_failure_signal(is_service_unavailable=True, http_status=503)
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    assert exc_info.value.retryable is True
@pytest.mark.prv_tc("014")
def test_prv_tc_014_network_error_is_transient(provider_env_keys: None) -> None:
    """PRV-TC-014: connection failure raises ProviderNetworkError retryable=True."""
    config = minimal_provider_config()
    signal = stub_failure_signal(is_connection_error=True)
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderNetworkError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    assert exc_info.value.retryable is True
@pytest.mark.prv_tc("015")
def test_prv_tc_015_schema_validation_error_is_permanent(
    provider_env_keys: None,
) -> None:
    """PRV-TC-015: FINJ-PRV-INVALID raises ProviderSchemaValidationError."""
    config = minimal_provider_config(
        failure_injection_enabled=True,
        active_injections=frozenset({InjectionId.FINJ_PRV_INVALID}),
    )

    def _raise_schema(_context: object | None = None) -> None:
        raise ProviderSchemaValidationError("invalid schema", provider_id=ProviderId.OPENAI)

    registry = build_finj_registry(
        config,
        hooks={InjectionId.FINJ_PRV_INVALID: _raise_schema},
    )
    fake = create_fake_provider(config, registry=registry)

    with pytest.raises(ProviderSchemaValidationError) as exc_info:
        fake.generate(valid_generate_request())

    assert exc_info.value.retryable is False
@pytest.mark.prv_tc("016")
def test_prv_tc_016_unknown_error_defaults_non_retryable(
    provider_env_keys: None,
) -> None:
    """PRV-TC-016: unmapped failure raises ProviderUnknownError retryable=False."""
    config = minimal_provider_config()
    signal = stub_failure_signal(exception_type="vendor.WeirdError")
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderUnknownError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    assert exc_info.value.error_class == ProviderErrorClass.UNKNOWN
    assert exc_info.value.retryable is False
@pytest.mark.prv_tc("017")
def test_prv_tc_017_default_retryable_matches_taxonomy() -> None:
    """PRV-TC-017: default_retryable matches contract §5 table."""
    expected = {
        ProviderErrorClass.TIMEOUT: True,
        ProviderErrorClass.RATE_LIMIT: True,
        ProviderErrorClass.AUTHENTICATION: False,
        ProviderErrorClass.PROVIDER_UNAVAILABLE: True,
        ProviderErrorClass.PROVIDER_ERROR: False,
        ProviderErrorClass.NETWORK_ERROR: True,
        ProviderErrorClass.SCHEMA_VALIDATION: False,
        ProviderErrorClass.UNKNOWN: False,
    }
    for error_class, retryable in expected.items():
        assert default_retryable(error_class) is retryable
@pytest.mark.prv_tc("018")
def test_prv_tc_018_error_messages_omit_secrets(provider_env_keys: None) -> None:
    """PRV-TC-018: authentication error message excludes API key value."""
    secret = "super-secret-auth-key-value"
    config = minimal_provider_config()
    signal = stub_failure_signal(
        is_auth_error=True,
        vendor_message=f"invalid key {secret}",
        http_status=401,
    )
    transport = make_stub_transport(result=signal)

    with pytest.raises(ProviderAuthenticationError) as exc_info:
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )

    message = str(exc_info.value)
    assert secret not in message
@pytest.mark.prv_tc("020")
def test_prv_tc_020_timeout_enforced_from_app_config(
    short_timeout_config: object,
) -> None:
    """PRV-TC-020: short timeout + slow stub raises ProviderTimeoutError."""
    config = short_timeout_config
    transport = make_stub_transport(
        result=stub_success_result(),
        sleep_seconds=1.0,
    )

    with pytest.raises(ProviderTimeoutError):
        generate_with_stub_transport(
            provider_id=ProviderId.OPENAI,
            config=config,
            transport=transport,
            request=valid_generate_request(),
        )
@pytest.mark.prv_tc("021")
def test_prv_tc_021_finj_prv_timeout_surfaces_timeout_error(
    provider_env_keys: None,
) -> None:
    """PRV-TC-021: FINJ-PRV-TIMEOUT raises ProviderTimeoutError without network."""
    config = minimal_provider_config(
        failure_injection_enabled=True,
        active_injections=frozenset({InjectionId.FINJ_PRV_TIMEOUT}),
    )

    def _raise_timeout(_context: object | None = None) -> None:
        raise ProviderTimeoutError("injected timeout", provider_id=ProviderId.FAKE)

    registry = build_finj_registry(
        config,
        hooks={InjectionId.FINJ_PRV_TIMEOUT: _raise_timeout},
    )
    fake = create_fake_provider(config, registry=registry)

    with pytest.raises(ProviderTimeoutError):
        fake.generate(valid_generate_request())
@pytest.mark.prv_tc("030")
def test_prv_tc_030_fake_provider_succeeds_without_network(
    provider_env_keys: None,
) -> None:
    """PRV-TC-030: create_provider(FAKE) returns success without HTTP."""
    config = minimal_provider_config()
    fake = create_provider(provider_id=ProviderId.FAKE, config=config)

    response = fake.generate(valid_generate_request())

    assert isinstance(response, GenerateResponse)
@pytest.mark.prv_tc("031")
def test_prv_tc_031_fake_provider_programmable_success(
    provider_env_keys: None,
) -> None:
    """PRV-TC-031: set_next_response returns programmed GenerateResponse."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    custom = programmed_fake_response(content="custom success")
    fake.set_next_response(custom)

    response = fake.generate(valid_generate_request())

    assert response.content == "custom success"
@pytest.mark.prv_tc("032")
def test_prv_tc_032_fake_provider_programmable_failure_modes(
    provider_env_keys: None,
) -> None:
    """PRV-TC-032: sequential set_next_error raises matching ProviderError subclasses."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    request = valid_generate_request()
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
@pytest.mark.prv_tc("033")
def test_prv_tc_033_fake_provider_reset_clears_state(
    provider_env_keys: None,
) -> None:
    """PRV-TC-033: reset() after programmed error restores default stub success."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    fake.set_next_error(ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE))
    fake.reset()

    response = fake.generate(valid_generate_request())

    assert response.content
@pytest.mark.prv_tc("040")
def test_prv_tc_040_latency_recorded_on_success(provider_env_keys: None) -> None:
    """PRV-TC-040: successful fake generation reports latency_ms > 0."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)

    response = fake.generate(valid_generate_request())

    assert response.latency_ms > 0
@pytest.mark.prv_tc("041")
def test_prv_tc_041_latency_recorded_on_failure_path(
    provider_env_keys: None,
) -> None:
    """PRV-TC-041: timeout failure emits telemetry duration before raise."""
    config = minimal_provider_config()
    transport = make_stub_transport(
        result=ProviderTimeoutError("timeout", provider_id=ProviderId.OPENAI),
        sleep_seconds=0.01,
    )
    provider, telemetry = setup_recording_provider(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=transport,
    )

    with pytest.raises(ProviderTimeoutError):
        provider.generate(valid_generate_request())

    assert telemetry.call_failed
    assert telemetry.call_failed[0]["latency_ms"] > 0
@pytest.mark.prv_tc("042")
def test_prv_tc_042_token_usage_captured_when_available(
    provider_env_keys: None,
) -> None:
    """PRV-TC-042: programmed response token counts appear on GenerateResponse."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    fake.set_next_response(
        programmed_fake_response(
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ),
    )

    response = fake.generate(valid_generate_request())

    assert response.token_usage == TokenUsage(input_tokens=100, output_tokens=50)
@pytest.mark.prv_tc("043")
def test_prv_tc_043_missing_token_metadata_omitted(
    provider_env_keys: None,
) -> None:
    """PRV-TC-043: stub transport with no token metadata yields token_usage=None."""
    config = minimal_provider_config()
    transport = make_stub_transport(result=stub_success_result(token_usage=None))

    response = generate_with_stub_transport(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=transport,
        request=valid_generate_request(),
    )

    assert response.token_usage is None
@pytest.mark.prv_tc("044")
def test_prv_tc_044_cost_estimate_when_pricing_configured(
    priced_openai_config: object,
) -> None:
    """PRV-TC-044: pricing + tokens produce non-None estimated_cost_usd."""
    config = priced_openai_config
    transport = make_stub_transport(
        result=stub_success_result(
            token_usage=TokenUsage(input_tokens=1000, output_tokens=500),
        ),
    )

    response = generate_with_stub_transport(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=transport,
        request=valid_generate_request(),
    )

    assert response.estimated_cost_usd is not None
    assert isinstance(response.estimated_cost_usd, Decimal)
@pytest.mark.prv_tc("045")
def test_prv_tc_045_cost_omitted_without_pricing(provider_env_keys: None) -> None:
    """PRV-TC-045: no pricing config yields estimated_cost_usd=None."""
    config = minimal_provider_config()
    transport = make_stub_transport(
        result=stub_success_result(
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ),
    )

    response = generate_with_stub_transport(
        provider_id=ProviderId.OPENAI,
        config=config,
        transport=transport,
        request=valid_generate_request(),
    )

    assert response.estimated_cost_usd is None
@pytest.mark.prv_tc("046")
def test_prv_tc_046_failed_call_exposes_error_class_for_telemetry(
    provider_env_keys: None,
) -> None:
    """PRV-TC-046: classified ProviderError exposes error_class and retryable."""
    config = minimal_provider_config()
    fake = create_fake_provider(config)
    fake.set_next_error(
        ProviderRateLimitError("rate limited", provider_id=ProviderId.FAKE),
    )

    with pytest.raises(ProviderError) as exc_info:
        fake.generate(valid_generate_request())

    assert exc_info.value.error_class == ProviderErrorClass.RATE_LIMIT
    assert exc_info.value.retryable is True
@pytest.mark.prv_tc("050")
def test_prv_tc_050_client_side_rate_limit_enforced(
    provider_env_keys: None,
) -> None:
    """PRV-TC-050: rate_limit_per_minute=1 blocks second rapid generate on FAKE."""
    config = minimal_provider_config(fake_rate_limit_per_minute=1)
    fake = create_fake_provider(config)
    request = valid_generate_request()

    fake.generate(request)
    with pytest.raises(ProviderRateLimitError):
        fake.generate(request)
@pytest.mark.prv_tc("051")
def test_prv_tc_051_finj_prv_rate_surfaces_rate_limit(
    provider_env_keys: None,
) -> None:
    """PRV-TC-051: FINJ-PRV-RATE raises ProviderRateLimitError."""
    config = minimal_provider_config(
        failure_injection_enabled=True,
        active_injections=frozenset({InjectionId.FINJ_PRV_RATE}),
    )

    def _raise_rate(_context: object | None = None) -> None:
        raise ProviderRateLimitError("injected rate", provider_id=ProviderId.FAKE)

    registry = build_finj_registry(
        config,
        hooks={InjectionId.FINJ_PRV_RATE: _raise_rate},
    )
    fake = create_fake_provider(config, registry=registry)

    with pytest.raises(ProviderRateLimitError):
        fake.generate(valid_generate_request())
@pytest.mark.prv_tc("060")
def test_prv_tc_060_telemetry_excludes_prompts_and_responses(
    provider_env_keys: None,
) -> None:
    """PRV-TC-060: emitted logs/metrics exclude prompt and response text."""
    from observability import get_logger
    from observability.fakes import InMemoryLogger

    config = minimal_provider_config()
    prompt_text = "TOP_SECRET_PROMPT_DO_NOT_LOG"
    request = valid_generate_request(
        messages=(
            ProviderMessage(role=ProviderMessageRole.USER, content=prompt_text),
        ),
    )

    with recording_observability():
        _, telemetry = generate_with_recording_telemetry(
            provider_id=ProviderId.FAKE,
            config=config,
            request=request,
        )

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert prompt_text not in joined
        for record in telemetry.delegated_calls:
            assert prompt_text not in str(record)
@pytest.mark.prv_tc("061")
def test_prv_tc_061_configuration_error_omits_credential_value() -> None:
    """PRV-TC-061: missing credential names env var only, not secret value."""
    secret = "must-not-appear-in-error"
    config = minimal_provider_config()

    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_provider(provider_id=ProviderId.OPENAI, config=config)

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert secret not in message
@pytest.mark.prv_tc("070")
def test_prv_tc_070_request_response_types_frozen() -> None:
    """PRV-TC-070: GenerateRequest and GenerateResponse are immutable."""
    request = valid_generate_request()
    response = programmed_fake_response()

    with pytest.raises(FrozenInstanceError):
        request.model = "mutated"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        response.content = "mutated"  # type: ignore[misc]
