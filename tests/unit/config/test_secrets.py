"""Unit tests for CFG-005 — SecretScanner (S1b)."""

from __future__ import annotations

import copy
import re

import pytest

from config.errors import ConfigSecretDetectedError
from config.messages import secret_detected_message
from config.secrets import SecretPattern, SecretScanner


def test_openai_api_key_pattern_detected() -> None:
    """CFG-TC-001 / LLD §8 pattern 1: sk- prefix with minimum total length 20."""
    secret_value = "sk-12345678901234567"
    tree: dict[str, object] = {"providers": {"openai": {"api_key": secret_value}}}
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"
    assert exc_info.value.key_path == "providers.openai.api_key"
    expected_message = secret_detected_message(
        key_path="providers.openai.api_key",
        pattern_name="openai_api_key",
    )
    assert str(exc_info.value) == expected_message
    assert secret_value not in str(exc_info.value)


def test_anthropic_api_key_pattern_detected() -> None:
    """LLD §8 pattern 2: sk-ant- prefix key."""
    tree: dict[str, object] = {
        "providers": {"anthropic": {"token": "sk-ant-1234567890abcdef"}},
    }
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"
    assert "anthropic" in exc_info.value.key_path


def test_pem_private_key_pattern_detected() -> None:
    """LLD §8 pattern 3: PEM private key block (re.DOTALL)."""
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAfake\n-----END RSA PRIVATE KEY-----"
    tree: dict[str, object] = {"tls": {"private_key": pem}}
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"
    assert exc_info.value.key_path == "tls.private_key"


def test_inline_credential_assignment_pattern_detected() -> None:
    """LLD §8 pattern 4: inline key=value or key: value assignment."""
    tree: dict[str, object] = {
        "debug": {"note": "api_key=supersecret12345678"},
    }
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"


def test_high_entropy_secret_field_pattern_detected() -> None:
    """LLD §8 pattern 5: long base64-like blob under suspicious key name."""
    blob = "AbCdEfGh" * 5  # mixed case; avoids ENV_VAR_NAME_PATTERN false exemption
    tree: dict[str, object] = {"storage": {"db_password": blob}}
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"
    assert exc_info.value.key_path == "storage.db_password"


def test_env_var_name_value_exempt_from_detection() -> None:
    """Env-var name exemption: OPENAI_API_KEY must not trigger secret detection."""
    tree: dict[str, object] = {
        "providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}},
    }
    scanner = SecretScanner()

    scanner.scan(tree)


def test_short_placeholder_not_detected_as_openai_key() -> None:
    """Negative: short sk- placeholder below LLD §8 minimum length."""
    tree: dict[str, object] = {"note": "sk-short"}
    scanner = SecretScanner()

    scanner.scan(tree)


def test_file_path_not_detected_as_secret() -> None:
    """Negative: filesystem path strings must not trigger secret heuristics."""
    tree: dict[str, object] = {
        "agents": {"topic_selector": {"prompt_file": "/etc/config/prompts/topic.txt"}},
    }
    scanner = SecretScanner()

    scanner.scan(tree)


def test_key_path_prefix_reported() -> None:
    """Scanner reports dot-path key_path including key_path_prefix."""
    tree: dict[str, object] = {"api_key": "sk-12345678901234567890"}
    scanner = SecretScanner()

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree, key_path_prefix="providers.openai")

    assert exc_info.value.key_path == "providers.openai.api_key"


def test_empty_patterns_allow_secret_shaped_value() -> None:
    """Injectable patterns=[] disables detection for secret-shaped values."""
    tree: dict[str, object] = {"providers": {"openai": {"api_key": "sk-12345678901234567"}}}
    scanner = SecretScanner(patterns=[])

    scanner.scan(tree)


def test_custom_pattern_first_match_ordering() -> None:
    """Custom pattern list uses first-match ordering with distinctive pattern name."""
    custom_pattern = SecretPattern(
        name="custom_test_pattern",
        pattern=re.compile(r"^CUSTOM-SECRET-[A-Za-z0-9]+$"),
    )
    tree: dict[str, object] = {"token": "CUSTOM-SECRET-abc1234567890"}
    scanner = SecretScanner(patterns=[custom_pattern])

    with pytest.raises(ConfigSecretDetectedError) as exc_info:
        scanner.scan(tree)

    assert exc_info.value.code == "CFG_SECRET"
    assert exc_info.value.key_path == "token"
    assert str(exc_info.value) == secret_detected_message(
        key_path="token",
        pattern_name="custom_test_pattern",
    )


def test_scanner_does_not_mutate_input_tree() -> None:
    """Scanner must not mutate the input RawConfigTree."""
    tree: dict[str, object] = {"providers": {"openai": {"api_key_env": "OPENAI_API_KEY"}}}
    before = copy.deepcopy(tree)
    scanner = SecretScanner()

    scanner.scan(tree)

    assert tree == before
