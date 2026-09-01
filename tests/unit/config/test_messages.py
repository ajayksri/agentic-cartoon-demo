"""Unit tests for CFG-002 — error message helpers (LLD §3.10)."""

from __future__ import annotations

import inspect

import pytest

from config.messages import (
    credential_message,
    prompt_message,
    secret_detected_message,
    validation_message,
)

_FAKE_SECRET = "sk-supersecret1234567890abcdef"


@pytest.mark.parametrize(
    ("key_path", "reason", "constraint", "expected"),
    [
        (
            "workflow.max_scenario_revisions",
            "must be a positive integer",
            "integer > 0",
            "workflow.max_scenario_revisions: must be a positive integer. Expected: integer > 0",
        ),
        (
            "agents.topic_selector.provider",
            "unknown provider id",
            "one of: openai, anthropic, gemini, kimi, fake",
            "agents.topic_selector.provider: unknown provider id. Expected: one of: openai, anthropic, gemini, kimi, fake",
        ),
    ],
    ids=["numeric_constraint", "referential_constraint"],
)
def test_validation_message_shape(
    key_path: str,
    reason: str,
    constraint: str,
    expected: str,
) -> None:
    assert validation_message(key_path=key_path, reason=reason, constraint=constraint) == expected
    assert key_path in expected
    assert reason in expected
    assert f"Expected: {constraint}" in expected


@pytest.mark.parametrize(
    ("env_var_name", "expected"),
    [
        (
            "OPENAI_API_KEY",
            "Required credential environment variable is unset or empty: OPENAI_API_KEY",
        ),
        (
            "POSTGRES_PASSWORD",
            "Required credential environment variable is unset or empty: POSTGRES_PASSWORD",
        ),
    ],
    ids=["provider_key", "postgres_password"],
)
def test_credential_message_shape(env_var_name: str, expected: str) -> None:
    assert credential_message(env_var_name=env_var_name) == expected
    assert env_var_name in expected


@pytest.mark.parametrize(
    ("key_path", "prompt_file", "expected"),
    [
        (
            "agents.topic_selector.prompt_file",
            "/etc/prompts/topic_selector.txt",
            "agents.topic_selector.prompt_file: Prompt file not found at path '/etc/prompts/topic_selector.txt'. Expected: existing file on local filesystem",
        ),
        (
            "agents.critic.prompt_file",
            "prompts/missing.md",
            "agents.critic.prompt_file: Prompt file not found at path 'prompts/missing.md'. Expected: existing file on local filesystem",
        ),
    ],
    ids=["absolute_path", "relative_path"],
)
def test_prompt_message_shape(key_path: str, prompt_file: str, expected: str) -> None:
    message = prompt_message(key_path=key_path, prompt_file=prompt_file)
    assert message == expected
    assert key_path in message
    assert f"'{prompt_file}'" in message
    assert "Expected: existing file on local filesystem" in message


@pytest.mark.parametrize(
    ("key_path", "pattern_name", "expected"),
    [
        (
            "providers.openai.api_key",
            "openai_api_key",
            "providers.openai.api_key: Inline secret pattern detected (openai_api_key). Expected: reference credentials via environment variable names, not inline values",
        ),
        (
            "tls.private_key",
            "pem_private_key",
            "tls.private_key: Inline secret pattern detected (pem_private_key). Expected: reference credentials via environment variable names, not inline values",
        ),
    ],
    ids=["openai_pattern", "pem_pattern"],
)
def test_secret_detected_message_shape(
    key_path: str,
    pattern_name: str,
    expected: str,
) -> None:
    message = secret_detected_message(key_path=key_path, pattern_name=pattern_name)
    assert message == expected
    assert key_path in message
    assert f"({pattern_name})" in message
    assert (
        "Expected: reference credentials via environment variable names, not inline values"
        in message
    )


def test_structured_helpers_do_not_accept_reason_parameter() -> None:
    """Helpers other than validation_message take structured fields only."""
    for helper in (credential_message, prompt_message, secret_detected_message):
        params = inspect.signature(helper).parameters
        assert "reason" not in params


@pytest.mark.parametrize(
    "helper,kwargs",
    [
        (credential_message, {"env_var_name": "OPENAI_API_KEY"}),
        (
            prompt_message,
            {
                "key_path": "agents.topic_selector.prompt_file",
                "prompt_file": "/prompts/topic.txt",
            },
        ),
        (
            secret_detected_message,
            {
                "key_path": "providers.openai.api_key",
                "pattern_name": "openai_api_key",
            },
        ),
    ],
    ids=["credential", "prompt", "secret_detected"],
)
def test_structured_helpers_never_embed_simulated_secret(
    helper: object,
    kwargs: dict[str, str],
) -> None:
    message = helper(**kwargs)  # type: ignore[operator]
    assert _FAKE_SECRET not in message
