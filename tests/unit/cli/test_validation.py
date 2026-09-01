"""Unit tests for CLI validation."""

from __future__ import annotations

import pytest

from api.types import InitiateWorkflowApiRequest
from cli.errors import CliUsageError
from cli.validation import InputValidator


@pytest.fixture
def validator() -> InputValidator:
    return InputValidator()


def test_validate_workflow_id_rejects_empty(validator: InputValidator) -> None:
    with pytest.raises(CliUsageError):
        validator.validate_workflow_id("   ", required=True)


def test_validate_initiate_fields_requires_one_field(validator: InputValidator) -> None:
    with pytest.raises(CliUsageError):
        validator.validate_initiate_fields(
            workflow_id=None,
            correlation_id=None,
            actor=None,
        )


def test_validate_initiate_fields_builds_request(validator: InputValidator) -> None:
    request = validator.validate_initiate_fields(
        workflow_id=None,
        correlation_id=None,
        actor="operator",
    )
    assert isinstance(request, InitiateWorkflowApiRequest)
    assert request.actor == "operator"


def test_validate_approval_action_rejects_unknown(validator: InputValidator) -> None:
    with pytest.raises(CliUsageError):
        validator.validate_approval_action("INVALID")


def test_sanitize_rejects_control_chars(validator: InputValidator) -> None:
    with pytest.raises(CliUsageError):
        validator._sanitize_printable_ascii(
            "bad\x01value",
            field="actor",
            max_len=256,
        )
