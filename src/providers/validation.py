"""Pre-provider request validation."""

# GUARDRAIL: Input — validate provider requests before sending to external LLM APIs.

from __future__ import annotations

from .types import GenerateRequest


class RequestValidator:
    def validate(self, request: GenerateRequest) -> None:
        if len(request.messages) == 0:
            raise ValueError("messages must not be empty")
        if request.model.strip() == "":
            raise ValueError("model must not be empty")
