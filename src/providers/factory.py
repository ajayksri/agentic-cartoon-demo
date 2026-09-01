"""Provider adapter factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from config.errors import ConfigCredentialMissingError
from config.types import AppConfig, ProviderConfig, ProviderId, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry

from .errors import ProviderConfigurationError
from .messages import configuration_error_message
from .protocols import ModelProvider
from .telemetry import ProviderTelemetry

if TYPE_CHECKING:
    from .vendors._transport import VendorTransport


def create_provider(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    registry: FailureInjectionRegistry | None = None,
) -> ModelProvider:
    provider_config, timeout_config, api_key = _resolve_provider_inputs(
        provider_id=provider_id,
        config=config,
    )
    return _build_adapter(
        provider_id=provider_id,
        provider_config=provider_config,
        timeout_config=timeout_config,
        api_key=api_key,
        registry=registry,
        transport_override=None,
    )


def _build_adapter(
    *,
    provider_id: ProviderId,
    provider_config: ProviderConfig,
    timeout_config: TimeoutConfig,
    api_key: str,
    registry: FailureInjectionRegistry | None,
    transport_override: VendorTransport | None = None,
    telemetry: ProviderTelemetry | None = None,
) -> ModelProvider:
    common = {
        "provider_config": provider_config,
        "timeout_config": timeout_config,
        "registry": registry,
    }
    if telemetry is not None:
        common["telemetry"] = telemetry

    if provider_id is ProviderId.FAKE:
        from .fake import FakeProvider

        return FakeProvider(**common)

    if provider_id is ProviderId.OPENAI:
        from .vendors.openai import OpenAIAdapter

        return OpenAIAdapter(
            api_key=api_key,
            transport=transport_override,
            **common,
        )

    if provider_id is ProviderId.ANTHROPIC:
        from .vendors.anthropic import AnthropicAdapter

        return AnthropicAdapter(
            api_key=api_key,
            transport=transport_override,
            **common,
        )

    if provider_id is ProviderId.GEMINI:
        from .vendors.gemini import GeminiAdapter

        return GeminiAdapter(
            api_key=api_key,
            transport=transport_override,
            **common,
        )

    if provider_id is ProviderId.KIMI:
        from .vendors.kimi import KimiAdapter

        return KimiAdapter(
            api_key=api_key,
            transport=transport_override,
            **common,
        )

    raise ProviderConfigurationError(
        configuration_error_message(
            provider_id=provider_id,
            reason="not configured",
        ),
        provider_id=provider_id,
    )


def _create_provider_for_tests(
    *,
    provider_id: ProviderId,
    config: AppConfig,
    transport: VendorTransport | None = None,
    registry: FailureInjectionRegistry | None = None,
    telemetry: ProviderTelemetry | None = None,
) -> ModelProvider:
    provider_config, timeout_config, api_key = _resolve_provider_inputs(
        provider_id=provider_id,
        config=config,
    )
    return _build_adapter(
        provider_id=provider_id,
        provider_config=provider_config,
        timeout_config=timeout_config,
        api_key=api_key,
        registry=registry,
        transport_override=transport,
        telemetry=telemetry,
    )


def _resolve_provider_inputs(
    *,
    provider_id: ProviderId,
    config: AppConfig,
) -> tuple[ProviderConfig, TimeoutConfig, str]:
    try:
        provider_config = config.get_provider_config(provider_id)
    except KeyError as exc:
        raise ProviderConfigurationError(
            configuration_error_message(
                provider_id=provider_id,
                reason="not configured",
            ),
            provider_id=provider_id,
        ) from exc

    if provider_id not in config.timeouts:
        raise ProviderConfigurationError(
            configuration_error_message(
                provider_id=provider_id,
                reason="timeout config missing",
            ),
            provider_id=provider_id,
        )
    timeout_config = config.timeouts[provider_id]

    if provider_id is ProviderId.FAKE:
        return provider_config, timeout_config, ""

    try:
        api_key = config.resolve_credential(provider_config.api_key_env)
    except (KeyError, ConfigCredentialMissingError) as exc:
        raise ProviderConfigurationError(
            f"PRV_CONFIG: missing credential env {provider_config.api_key_env} "
            f"for provider {provider_id.value}",
            provider_id=provider_id,
        ) from exc

    return provider_config, timeout_config, api_key
