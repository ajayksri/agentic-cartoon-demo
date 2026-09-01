"""Pre-code test mold for OBS-003 — secret redaction pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from observability.types import LogEnvelope


@pytest.mark.ct_obs("CT-OBS-006")
def test_r001_openai_key_scrubbed_to_placeholder() -> None:
    """CT-OBS-006: R-001 OpenAI-style API key is scrubbed to a safe placeholder."""
    from observability.redaction import scrub_string

    raw = "prefix sk-abcdefghijklmnopqrstuvwxyz123456 suffix"
    scrubbed = scrub_string(raw)

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in scrubbed
    assert "[REDACTED:api_key]" in scrubbed


@pytest.mark.ct_obs("CT-OBS-006")
def test_r003_bearer_token_scrubbed() -> None:
    """CT-OBS-006: R-003 Bearer token is scrubbed to a safe placeholder."""
    from observability.redaction import scrub_string

    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token.sig"
    scrubbed = scrub_string(raw)

    assert "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token.sig" not in scrubbed
    assert "[REDACTED:token]" in scrubbed


@pytest.mark.ct_obs("CT-OBS-006")
def test_unredactable_full_secret_message_raises() -> None:
    """CT-OBS-006: entirely secret message raises RedactionRequiredError."""
    from observability.errors import RedactionRequiredError
    from observability.redaction import redact_log_envelope

    envelope = LogEnvelope(
        event="provider_call_failed",
        level="INFO",
        timestamp=datetime(2026, 8, 30, tzinfo=timezone.utc),
        message="sk-abcdefghijklmnopqrstuvwxyz1234567890",
        service_name="test-service",
    )

    with pytest.raises(RedactionRequiredError):
        redact_log_envelope(envelope)


@pytest.mark.ct_obs("CT-OBS-008")
def test_label_secret_raises_high_cardinality_label_error() -> None:
    """CT-OBS-008: secret-like metric label value raises HighCardinalityLabelError."""
    from observability.errors import HighCardinalityLabelError
    from observability.redaction import redact_label_values

    labels = {"provider": "sk-abcdefghijklmnopqrstuvwxyz1234567890"}

    with pytest.raises(HighCardinalityLabelError):
        redact_label_values(labels)


def test_r002_aws_access_key_scrubbed() -> None:
    """R-002: AWS access key is scrubbed to a safe placeholder."""
    from observability.redaction import scrub_string

    raw = "prefix AKIAIOSFODNN7EXAMPLE suffix"
    scrubbed = scrub_string(raw)

    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "[REDACTED:api_key]" in scrubbed


def test_r004_jwt_scrubbed() -> None:
    """R-004: JWT token is scrubbed to a safe placeholder."""
    from observability.redaction import scrub_string

    raw = (
        "token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    scrubbed = scrub_string(raw)

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed
    assert "[REDACTED:jwt]" in scrubbed


def test_r005_api_key_assignment_scrubbed() -> None:
    """R-005: assignment-style api_key value is scrubbed."""
    from observability.redaction import scrub_string

    raw = "config api_key=supersecretvalue123"
    scrubbed = scrub_string(raw)

    assert "supersecretvalue123" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_r006_authorization_header_scrubbed() -> None:
    """R-006: authorization header assignment is scrubbed."""
    from observability.redaction import scrub_string

    raw = "authorization: Bearer sometokenvalue"
    scrubbed = scrub_string(raw)

    assert "sometokenvalue" not in scrubbed
    assert "[REDACTED:token]" in scrubbed


def test_r007_env_style_secret_scrubbed() -> None:
    """R-007: env-style password/secret assignment is scrubbed."""
    from observability.redaction import scrub_string

    raw = "env password=supersecret123"
    scrubbed = scrub_string(raw)

    assert "supersecret123" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_r008_hex_scrubbed_under_credential_like_attribute_key() -> None:
    """R-008: hex secret under credential-like attribute key is scrubbed."""
    from observability.redaction import REDACTION_PLACEHOLDER, redact_attribute_map

    hex_secret = "deadbeefdeadbeefdeadbeefdeadbeef"
    result = redact_attribute_map({"api_key": f"prefix {hex_secret} suffix"})

    assert hex_secret not in result["api_key"]
    assert REDACTION_PLACEHOLDER in result["api_key"]


def test_redact_log_envelope_scrubs_message_and_attributes() -> None:
    """redact_log_envelope scrubs secret patterns in attributes and message."""
    from observability.redaction import redact_log_envelope

    envelope = LogEnvelope(
        event="provider_call_failed",
        level="INFO",
        timestamp=datetime(2026, 8, 30, tzinfo=timezone.utc),
        message="call completed with token in context",
        service_name="test-service",
        attributes={
            "note": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token.sig",
            "count": 42,
        },
    )

    result = redact_log_envelope(envelope)

    assert "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token.sig" not in result.attributes["note"]
    assert "[REDACTED:token]" in result.attributes["note"]
    assert result.attributes["count"] == 42
    assert result.message == envelope.message


def test_redact_attribute_map_scrubs_partial_secret() -> None:
    """redact_attribute_map scrubs partial-context secret values."""
    from observability.redaction import redact_attribute_map

    result = redact_attribute_map(
        {
            "detail": "prefix sk-abcdefghijklmnopqrstuvwxyz123456 suffix",
            "attempt": 2,
        }
    )

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result["detail"]
    assert "[REDACTED:api_key]" in result["detail"]
    assert result["attempt"] == 2


def test_redact_attribute_map_raises_on_entirely_secret_value() -> None:
    """redact_attribute_map raises RedactionRequiredError on unredactable values."""
    from observability.errors import RedactionRequiredError
    from observability.redaction import redact_attribute_map

    with pytest.raises(RedactionRequiredError):
        redact_attribute_map({"api_key": "sk-abcdefghijklmnopqrstuvwxyz1234567890"})


def test_r008_hex_unchanged_under_non_credential_attribute_key() -> None:
    """R-008: hex value under non-credential key is left unchanged."""
    from observability.redaction import redact_attribute_map

    hex_value = "deadbeefdeadbeefdeadbeefdeadbeef"
    result = redact_attribute_map({"status": hex_value})

    assert result["status"] == hex_value
