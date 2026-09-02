"""Unit tests for API request validation."""

from __future__ import annotations

import pytest

from api.errors import ApiValidationError
from api.validation import RequestValidator
from workflow.types import ApprovalAction


@pytest.fixture
def validator() -> RequestValidator:
    return RequestValidator()


def test_validate_approval_body_accepts_lowercase_action(validator: RequestValidator) -> None:
    request = validator.validate_approval_body(
        action="approve",
        actor="local-demo",
        idempotency_key=None,
    )
    assert request.action == ApprovalAction.APPROVE
    assert request.actor == "local-demo"
