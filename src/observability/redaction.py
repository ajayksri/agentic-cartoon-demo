"""Secret pattern catalog and scrub helpers (LLD §9)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Safe observability — prompts, API keys, and tokens
# are redacted from logs and traces so production telemetry does not leak secrets.

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from re import Pattern

from observability.errors import HighCardinalityLabelError, RedactionRequiredError
from observability.types import LogEnvelope

REDACTION_PLACEHOLDER = "[REDACTED]"

FORBIDDEN_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "prompt",
        "response",
        "api_key",
        "token",
        "authorization",
        "password",
        "secret",
    }
)

FORBIDDEN_TRACE_ATTRIBUTE_KEYS: frozenset[str] = FORBIDDEN_LOG_FIELDS | frozenset(
    {
        "request_body",
        "response_body",
    }
)

_CREDENTIAL_LIKE_KEY_TERMS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "credential",
        "authorization",
    }
)

_R001_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")
_R002_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_R003_BEARER_TOKEN = re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b")
_R004_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_R005_API_KEY_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([^\s'\",]{8,})"
)
_R006_AUTHORIZATION_HEADER = re.compile(
    r"(?i)authorization\s*[:=]\s*['\"]?[^\s'\",]+"
)
_R007_ENV_STYLE_SECRET = re.compile(
    r"(?i)(password|secret|token|credential)\s*[:=]\s*['\"]?([^\s'\",]{4,})"
)
_R008_HEX_SECRET = re.compile(r"\b[0-9a-fA-F]{32,}\b")

# Compiled once at module load; order matches LLD §9.1 catalog.
_STRING_SCRUBBERS: tuple[tuple[Pattern[str], str], ...] = (
    (_R001_OPENAI_KEY, "[REDACTED:api_key]"),
    (_R002_AWS_ACCESS_KEY, "[REDACTED:api_key]"),
    (_R003_BEARER_TOKEN, "[REDACTED:token]"),
    (_R004_JWT, "[REDACTED:jwt]"),
)

_ASSIGNMENT_SCRUBBERS: tuple[Pattern[str], ...] = (
    _R005_API_KEY_ASSIGNMENT,
    _R006_AUTHORIZATION_HEADER,
    _R007_ENV_STYLE_SECRET,
)

_MATCH_PATTERNS: tuple[Pattern[str], ...] = (
    _R001_OPENAI_KEY,
    _R002_AWS_ACCESS_KEY,
    _R003_BEARER_TOKEN,
    _R004_JWT,
    _R005_API_KEY_ASSIGNMENT,
    _R006_AUTHORIZATION_HEADER,
    _R007_ENV_STYLE_SECRET,
)


def _is_credential_like_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(term in normalized for term in _CREDENTIAL_LIKE_KEY_TERMS)


def _repl_assignment(match: re.Match[str]) -> str:
    if match.re is _R006_AUTHORIZATION_HEADER:
        return "[REDACTED:token]"
    label = match.group(1)
    separator = ": " if ":" in match.group(0) else "="
    if separator.strip() == "=":
        separator = "="
    return f"{label}{separator}[REDACTED]"


def _apply_string_scrubbers(value: str, *, include_hex: bool, attribute_key: str | None = None) -> str:
    scrubbed = value
    for pattern, placeholder in _STRING_SCRUBBERS:
        scrubbed = pattern.sub(placeholder, scrubbed)
    for pattern in _ASSIGNMENT_SCRUBBERS:
        scrubbed = pattern.sub(_repl_assignment, scrubbed)
    if include_hex and (attribute_key is None or _is_credential_like_key(attribute_key)):
        scrubbed = _R008_HEX_SECRET.sub(REDACTION_PLACEHOLDER, scrubbed)
    return scrubbed


def _secret_span(value: str, *, include_hex: bool = False, attribute_key: str | None = None) -> tuple[int, int] | None:
    for pattern in _MATCH_PATTERNS:
        match = pattern.search(value)
        if match is not None:
            return match.start(), match.end()
    if include_hex and (attribute_key is None or _is_credential_like_key(attribute_key)):
        match = _R008_HEX_SECRET.search(value)
        if match is not None:
            return match.start(), match.end()
    return None


def _is_entirely_secret(value: str, *, include_hex: bool = False, attribute_key: str | None = None) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    span = _secret_span(stripped, include_hex=include_hex, attribute_key=attribute_key)
    if span is None:
        return False
    start, end = span
    return start == 0 and end == len(stripped)


def matches_secret_pattern(value: str) -> bool:
    """True if any R-* pattern matches."""
    return _secret_span(value) is not None


def scrub_string(value: str) -> str:
    """Apply all patterns; return scrubbed string."""
    return _apply_string_scrubbers(value, include_hex=False)


def _redact_string_value(value: str, *, attribute_key: str | None = None) -> str:
    if _is_entirely_secret(value, include_hex=attribute_key is not None, attribute_key=attribute_key):
        raise RedactionRequiredError(f"Unredactable secret in telemetry value")
    return _apply_string_scrubbers(
        value,
        include_hex=attribute_key is not None,
        attribute_key=attribute_key,
    )


def redact_log_envelope(envelope: LogEnvelope) -> LogEnvelope:
    """Scrub message and attributes; raise when values are entirely secret."""
    message = _redact_string_value(envelope.message)
    redacted_attributes: dict[str, str | int | float | bool] = {}
    for key, attr_value in envelope.attributes.items():
        if isinstance(attr_value, str):
            redacted_attributes[key] = _redact_string_value(attr_value, attribute_key=key)
        else:
            redacted_attributes[key] = attr_value
    if message == envelope.message and redacted_attributes == envelope.attributes:
        return envelope
    return replace(envelope, message=message, attributes=redacted_attributes)


def redact_attribute_map(
    attributes: Mapping[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    """Scrub string values; raise RedactionRequiredError on unredactable values."""
    redacted: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if isinstance(value, str):
            redacted[key] = _redact_string_value(value, attribute_key=key)
        else:
            redacted[key] = value
    return redacted


def redact_label_values(labels: Mapping[str, str]) -> Mapping[str, str]:
    """Raise HighCardinalityLabelError when a label value matches a secret pattern."""
    for key, value in labels.items():
        if matches_secret_pattern(value):
            raise HighCardinalityLabelError(
                f"Metric label {key!r} contains a secret-like value"
            )
    return dict(labels)
