"""Public agent error types."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.types import AgentId


class AgentError(Exception):
    """Base class for all agent module errors."""

    code: str = "AGT_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        agent_id: AgentId | None = None,
    ) -> None:
        super().__init__(message)
        self.agent_id = agent_id


class AgentInputValidationError(AgentError):
    """Structured input fails pre-provider validation."""

    code = "AGT_INPUT"
    retryable = False


class AgentOutputValidationError(AgentError):
    """Provider response fails output schema validation."""

    code = "AGT_OUTPUT"
    retryable = False


class AgentPromptLoadError(AgentError):
    """Prompt file missing or unreadable at execution time."""

    code = "AGT_PROMPT"
    retryable = False


class AgentConfigurationError(AgentError):
    """Missing agent config or invalid wiring."""

    code = "AGT_CONFIG"
    retryable = False
