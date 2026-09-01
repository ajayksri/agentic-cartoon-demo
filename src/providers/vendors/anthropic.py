"""Anthropic vendor adapter."""

from __future__ import annotations

from config.types import ProviderConfig, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry
from anthropic import Anthropic

from providers.base import BaseRemoteProvider
from providers.error_mapper import VendorErrorMapper
from providers.types import GenerateRequest, ProviderMessageRole, TokenUsage
from providers.internal_types import VendorCallResult, VendorTransportError
from providers.vendors._transport import VendorTransport


class AnthropicTransport:
    def __init__(self, *, api_key: str, client: Anthropic | None = None) -> None:
        self._client = client or Anthropic(api_key=api_key)

    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: object,
    ) -> VendorCallResult:
        from providers.timeout import TimeoutBudget

        assert isinstance(timeout, TimeoutBudget)
        budget = timeout

        client = self._client.with_options(timeout=budget.overall_deadline_seconds)
        system_message = None
        messages: list[dict[str, str]] = []
        for msg in request.messages:
            if msg.role is ProviderMessageRole.SYSTEM and system_message is None:
                system_message = msg.content
                continue
            role = "assistant" if msg.role is ProviderMessageRole.ASSISTANT else "user"
            messages.append({"role": role, "content": msg.content})

        kwargs: dict[str, object] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens or 1024,
        }
        if system_message is not None:
            kwargs["system"] = system_message
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        try:
            message = client.messages.create(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            signal = VendorErrorMapper.extract_anthropic_failure(exc)
            raise VendorTransportError(signal) from exc

        content = ""
        if message.content:
            content = getattr(message.content[0], "text", "") or ""
        model = getattr(message, "model", request.model)
        token_usage = None
        if message.usage is not None:
            token_usage = TokenUsage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
            )
        return VendorCallResult(content=content, model=model, token_usage=token_usage)


class AnthropicAdapter(BaseRemoteProvider):
    def __init__(
        self,
        *,
        api_key: str,
        provider_config: ProviderConfig,
        timeout_config: TimeoutConfig,
        registry: FailureInjectionRegistry | None = None,
        transport: VendorTransport | None = None,
        **base_kwargs: object,
    ) -> None:
        from config.types import ProviderId

        resolved_transport = transport or AnthropicTransport(api_key=api_key)
        super().__init__(
            provider_id=ProviderId.ANTHROPIC,
            provider_config=provider_config,
            timeout_config=timeout_config,
            registry=registry,
            transport=resolved_transport,
            **base_kwargs,  # type: ignore[arg-type]
        )
