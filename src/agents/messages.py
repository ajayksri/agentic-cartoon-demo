"""Bounded error message templates (MOD-AGT-INV-021)."""

from __future__ import annotations

from config.types import AgentId

_SENSITIVE_REASON_MARKERS = (
    "prompt",
    "response",
    "api_key",
    "api-key",
    "sk-",
    "secret",
    "top_secret",
)


def _bounded_reason(reason: str) -> str:
    """Return a bounded reason string safe for error messages (MOD-AGT-INV-021)."""
    lowered = reason.lower()
    if any(marker in lowered for marker in _SENSITIVE_REASON_MARKERS):
        return "validation failed"
    return reason


def input_validation_message(*, agent_id: AgentId, reason: str) -> str:
    return f"AGT_INPUT: agent={agent_id.value} — {_bounded_reason(reason)}"


def output_validation_message(*, agent_id: AgentId, reason: str) -> str:
    return f"AGT_OUTPUT: agent={agent_id.value} — {_bounded_reason(reason)}"


def prompt_load_message(*, agent_id: AgentId, reason: str) -> str:
    return f"AGT_PROMPT: agent={agent_id.value} — {_bounded_reason(reason)}"


def configuration_error_message(*, agent_id: AgentId, reason: str) -> str:
    return f"AGT_CONFIG: agent={agent_id.value} — {_bounded_reason(reason)}"
