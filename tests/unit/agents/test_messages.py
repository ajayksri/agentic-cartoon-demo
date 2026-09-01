"""Pre-code test mold for AGT-001 — error message helpers (LLD §4.9)."""

from __future__ import annotations

import pytest

from config.types import AgentId


_SECRET_PROMPT = "TOP_SECRET_PROMPT_DO_NOT_APPEAR"
_SECRET_RESPONSE = "TOP_SECRET_RESPONSE_DO_NOT_APPEAR"
_SECRET_KEY = "sk-super-secret-api-key-value"


def test_input_validation_message_shape() -> None:
    from agents.messages import input_validation_message

    message = input_validation_message(
        agent_id=AgentId.TOPIC_SELECTOR,
        reason="empty candidates",
    )
    assert message.startswith("AGT_INPUT:")
    assert "agent=topic_selector" in message
    assert "empty candidates" in message


def test_output_validation_message_shape() -> None:
    from agents.messages import output_validation_message

    message = output_validation_message(
        agent_id=AgentId.SCENARIO_GENERATOR,
        reason="invalid JSON",
    )
    assert message.startswith("AGT_OUTPUT:")
    assert "agent=scenario_generator" in message
    assert "invalid JSON" in message


def test_prompt_load_message_shape() -> None:
    from agents.messages import prompt_load_message

    message = prompt_load_message(
        agent_id=AgentId.CRITIC,
        reason="file not found",
    )
    assert message.startswith("AGT_PROMPT:")
    assert "agent=critic" in message
    assert "file not found" in message


def test_configuration_error_message_shape() -> None:
    from agents.messages import configuration_error_message

    message = configuration_error_message(
        agent_id=AgentId.TOPIC_SELECTOR,
        reason="provider mismatch",
    )
    assert message.startswith("AGT_CONFIG:")
    assert "agent=topic_selector" in message
    assert "provider mismatch" in message


def test_messages_do_not_leak_prompt_response_or_secrets() -> None:
    """MOD-AGT-INV-021: bounded messages exclude prompt/response/API key content."""
    from agents.messages import (
        configuration_error_message,
        input_validation_message,
        output_validation_message,
        prompt_load_message,
    )

    for helper in (
        input_validation_message,
        output_validation_message,
        prompt_load_message,
        configuration_error_message,
    ):
        message = helper(
            agent_id=AgentId.TOPIC_SELECTOR,
            reason=f"validation failed for {_SECRET_PROMPT} and {_SECRET_RESPONSE}",
        )
        assert _SECRET_PROMPT not in message
        assert _SECRET_RESPONSE not in message
        assert _SECRET_KEY not in message
