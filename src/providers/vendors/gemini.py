"""Gemini vendor adapter."""

from __future__ import annotations

from config.types import ProviderConfig, TimeoutConfig
from failure_injection.protocols import FailureInjectionRegistry
from google import genai

from providers.base import BaseRemoteProvider
from providers.error_mapper import VendorErrorMapper
from providers.types import GenerateRequest, ProviderMessageRole, TokenUsage
from providers.internal_types import VendorCallResult, VendorTransportError
from providers.vendors._transport import VendorTransport


class GeminiTransport:
    def __init__(self, *, api_key: str, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(api_key=api_key)

    def complete(
        self,
        request: GenerateRequest,
        *,
        timeout: object,
    ) -> VendorCallResult:
        from providers.timeout import TimeoutBudget

        assert isinstance(timeout, TimeoutBudget)
        budget = timeout

        system_instruction = None
        contents: list[dict[str, str | list[dict[str, str]]]] = []
        for msg in request.messages:
            if msg.role is ProviderMessageRole.SYSTEM and system_instruction is None:
                system_instruction = msg.content
                continue
            role = "model" if msg.role is ProviderMessageRole.ASSISTANT else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})

        config: dict[str, object] = {
            "http_options": {"timeout": int(budget.overall_deadline_seconds * 1000)},
        }
        if system_instruction is not None:
            config["system_instruction"] = system_instruction
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            config["max_output_tokens"] = request.max_output_tokens

        try:
            response = self._client.models.generate_content(
                model=request.model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            signal = VendorErrorMapper.extract_gemini_failure(exc)
            raise VendorTransportError(signal) from exc

        content = getattr(response, "text", "") or ""
        token_usage = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            token_usage = TokenUsage(
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
            )
        return VendorCallResult(content=content, model=request.model, token_usage=token_usage)


class GeminiAdapter(BaseRemoteProvider):
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

        resolved_transport = transport or GeminiTransport(api_key=api_key)
        super().__init__(
            provider_id=ProviderId.GEMINI,
            provider_config=provider_config,
            timeout_config=timeout_config,
            registry=registry,
            transport=resolved_transport,
            **base_kwargs,  # type: ignore[arg-type]
        )
