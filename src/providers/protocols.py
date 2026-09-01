"""Public provider protocol definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .errors import ProviderError
from .types import GenerateRequest, GenerateResponse

if TYPE_CHECKING:
    from config.types import AppConfig, ProviderId
    from failure_injection.protocols import FailureInjectionRegistry


@runtime_checkable
class ModelProvider(Protocol):
    """LLM completion adapter for a single provider backend."""

    @property
    def provider_id(self) -> ProviderId:
        """Stable identifier for this adapter."""
        ...

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Execute one LLM completion within configured timeout and rate limits."""
        ...


@runtime_checkable
class FakeProvider(ModelProvider, Protocol):
    """Test double with programmable success and failure outcomes."""

    def set_next_response(self, response: GenerateResponse) -> None:
        """Program the next generate call to return this response."""
        ...

    def set_next_error(self, error: ProviderError) -> None:
        """Program the next generate call to raise this error."""
        ...

    def reset(self) -> None:
        """Clear programmed outcomes and return to default stub behaviour."""
        ...
