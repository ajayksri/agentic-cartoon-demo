"""Internal error message templates for the config module."""

from __future__ import annotations


def validation_message(*, key_path: str, reason: str, constraint: str) -> str:
    return f"{key_path}: {reason}. Expected: {constraint}"


def credential_message(*, env_var_name: str) -> str:
    return f"Required credential environment variable is unset or empty: {env_var_name}"


def prompt_message(*, key_path: str, prompt_file: str) -> str:
    return validation_message(
        key_path=key_path,
        reason=f"Prompt file not found at path '{prompt_file}'",
        constraint="existing file on local filesystem",
    )


def secret_detected_message(*, key_path: str, pattern_name: str) -> str:
    return validation_message(
        key_path=key_path,
        reason=f"Inline secret pattern detected ({pattern_name})",
        constraint="reference credentials via environment variable names, not inline values",
    )
