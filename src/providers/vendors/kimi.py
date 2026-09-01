"""Kimi (Moonshot) vendor adapter — OpenAI-compatible API."""

from __future__ import annotations

from collections.abc import Mapping

from config.types import ProviderConfig, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry
from openai import OpenAI

from providers.base import BaseRemoteProvider
from providers.error_mapper import VendorErrorMapper
from providers.types import GenerateRequest, ProviderMessageRole, TokenUsage
from providers.internal_types import VendorCallResult, VendorTransportError
from providers.vendors._transport import VendorTransport

MOONSHOT_API_BASE_URL = "https://api.moonshot.cn/v1"

KIMI_ROLE_MAP: Mapping[ProviderMessageRole, str] = {
    ProviderMessageRole.SYSTEM: "system",
    ProviderMessageRole.USER: "user",
    ProviderMessageRole.ASSISTANT: "assistant",
}


class KimiTransport:
    def __init__(self, *, api_key: str, client: OpenAI | None = None) -> None:
        self._client = client or OpenAI(
            api_key=api_key,
            base_url=MOONSHOT_API_BASE_URL,
        )

    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: object,
    ) -> VendorCallResult:
        from providers.timeout import TimeoutBudget

        assert isinstance(timeout, TimeoutBudget)
        budget = timeout

        if budget.total_seconds is not None:
            timeout_value: float | object = budget.overall_deadline_seconds
        else:
            try:
                from openai import Timeout

                connect = budget.connect_seconds or budget.read_seconds
                timeout_value = Timeout(
                    connect=connect,
                    read=budget.read_seconds,
                    write=budget.read_seconds,
                    pool=5.0,
                )
            except Exception:
                timeout_value = budget.overall_deadline_seconds

        client = self._client.with_options(timeout=timeout_value)
        messages = [
            {"role": KIMI_ROLE_MAP[msg.role], "content": msg.content}
            for msg in request.messages
        ]
        kwargs: dict[str, object] = {"model": request.model, "messages": messages}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        try:
            completion = client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            signal = VendorErrorMapper.extract_openai_failure(exc)
            raise VendorTransportError(signal) from exc

        content = ""
        if completion.choices:
            message = completion.choices[0].message
            content = message.content or ""
        model = completion.model or request.model
        token_usage = None
        if completion.usage is not None:
            token_usage = TokenUsage(
                input_tokens=completion.usage.prompt_tokens,
                output_tokens=completion.usage.completion_tokens,
            )
        return VendorCallResult(content=content, model=model, token_usage=token_usage)


class KimiAdapter(BaseRemoteProvider):
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

        resolved_transport = transport or KimiTransport(api_key=api_key)
        super().__init__(
            provider_id=ProviderId.KIMI,
            provider_config=provider_config,
            timeout_config=timeout_config,
            registry=registry,
            transport=resolved_transport,
            **base_kwargs,  # type: ignore[arg-type]
        )
