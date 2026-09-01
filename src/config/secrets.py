"""Heuristic inline-secret detection for raw configuration trees."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from config.draft import RawConfigTree
from config.errors import ConfigSecretDetectedError
from config.messages import secret_detected_message

ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")

_SUSPICIOUS_KEY_PATTERN = re.compile(r"(?i).*(password|secret|token|api_key).*")


def _suspicious_key(key: str) -> bool:
    return _SUSPICIOUS_KEY_PATTERN.match(key) is not None


@dataclass(frozen=True, slots=True)
class SecretPattern:
    name: str
    pattern: re.Pattern[str]
    applies_to_key: Callable[[str], bool] | None = None


def _default_patterns() -> tuple[SecretPattern, ...]:
    return (
        SecretPattern(
            name="openai_api_key",
            pattern=re.compile(r"^sk-[A-Za-z0-9_-]{17,}$"),
        ),
        SecretPattern(
            name="anthropic_api_key",
            pattern=re.compile(r"^sk-ant-[A-Za-z0-9_-]{8,}$"),
        ),
        SecretPattern(
            name="pem_private_key",
            pattern=re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----", re.DOTALL),
        ),
        SecretPattern(
            name="inline_credential_assignment",
            pattern=re.compile(
                r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9/+=_-]{8,}"
            ),
        ),
        SecretPattern(
            name="high_entropy_secret_field",
            pattern=re.compile(r"^[A-Za-z0-9/+=_-]{40,}$"),
            applies_to_key=_suspicious_key,
        ),
    )


class SecretScanner:
    def __init__(self, patterns: Sequence[SecretPattern] | None = None) -> None:
        self._patterns = tuple(patterns) if patterns is not None else _default_patterns()

    def scan(self, tree: RawConfigTree, *, key_path_prefix: str = "") -> None:
        """Depth-first scan of string leaves; raises on first secret pattern match."""
        self._scan_node(tree, key_path_prefix)

    def _scan_node(self, node: object, key_path: str) -> None:
        if isinstance(node, str):
            self._scan_string(node, key_path)
        elif isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{key_path}.{key}" if key_path else str(key)
                self._scan_node(value, child_path)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                segment = str(index)
                child_path = f"{key_path}.{segment}" if key_path else segment
                self._scan_node(item, child_path)

    def _scan_string(self, value: str, key_path: str) -> None:
        if ENV_VAR_NAME_PATTERN.fullmatch(value):
            return

        key_name = key_path.rsplit(".", 1)[-1] if key_path else ""

        for secret_pattern in self._patterns:
            if secret_pattern.applies_to_key is not None and not secret_pattern.applies_to_key(
                key_name
            ):
                continue
            if self._matches_pattern(value, secret_pattern.pattern):
                raise ConfigSecretDetectedError(
                    secret_detected_message(
                        key_path=key_path,
                        pattern_name=secret_pattern.name,
                    ),
                    key_path=key_path,
                )

    @staticmethod
    def _matches_pattern(value: str, pattern: re.Pattern[str]) -> bool:
        compiled = pattern.pattern
        if compiled.startswith("^") and compiled.endswith("$"):
            return pattern.fullmatch(value) is not None
        return pattern.search(value) is not None
