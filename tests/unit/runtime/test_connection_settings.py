"""Unit tests for RT-006 — ConnectionSettingsBuilder (LLD §5)."""

from __future__ import annotations

import pytest

from config.errors import ConfigCredentialMissingError

from tests.unit.runtime.helpers import minimal_runtime_config


def test_connection_settings_builder_delegates_to_resolve_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLD §5: user/password resolved via AppConfig.resolve_credential."""
    from runtime.bootstrap import ConnectionSettingsBuilder

    monkeypatch.setenv("POSTGRES_USER", "runtime-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "runtime-pass")
    config = minimal_runtime_config()
    settings = ConnectionSettingsBuilder.from_app_config(config)

    assert settings.user == "runtime-user"
    assert settings.password == "runtime-pass"
    assert settings.host == config.infrastructure.postgres.host


def test_missing_credential_propagates_unchanged() -> None:
    """ConfigCredentialMissingError propagates without translation."""
    from unittest.mock import MagicMock

    from runtime.bootstrap import ConnectionSettingsBuilder

    base = minimal_runtime_config()
    config = MagicMock()
    config.infrastructure = base.infrastructure
    config.resolve_credential.side_effect = ConfigCredentialMissingError(
        "missing credential",
        env_var_name="MISSING_ENV",
    )

    with pytest.raises(ConfigCredentialMissingError):
        ConnectionSettingsBuilder.from_app_config(config)


def test_connection_settings_never_logs_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ACD-SEC-001 / RT-TC-024 seam: builder path omits credential values from logs."""
    from runtime.bootstrap import ConnectionSettingsBuilder

    monkeypatch.setenv("POSTGRES_USER", "runtime-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-value")
    config = minimal_runtime_config()
    ConnectionSettingsBuilder.from_app_config(config)

    combined = caplog.text.lower()
    assert "super-secret-value" not in combined
    assert "postgres_password" not in combined
