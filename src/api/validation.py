"""Pure REST input validation (MOD-API-INV-009)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: API idempotency keys — client-supplied keys on
# initiate/approval prevent duplicate workflows when HTTP clients retry on timeout.
# GUARDRAIL: Input — validate and bound all REST inputs before touching workflow engine.

from __future__ import annotations

from workflow.types import ApprovalAction

from .constants import (
    MAX_ACTOR_LEN,
    MAX_CORRELATION_ID_LEN,
    MAX_IDEMPOTENCY_KEY_LEN,
    MAX_WORKFLOW_ID_LEN,
    WORKFLOW_ID_PATTERN,
)
from .errors import ApiValidationError
from .types import InitiateWorkflowApiRequest, SubmitApprovalApiRequest


class RequestValidator:
    """Validates untrusted REST inputs before workflow delegation."""

    def validate_workflow_id(self, raw: str | None, *, field: str = "workflow_id") -> str:
        sanitized = self._sanitize_string(
            raw,
            field=field,
            max_len=MAX_WORKFLOW_ID_LEN,
            allow_empty=False,
        )
        assert sanitized is not None
        if not WORKFLOW_ID_PATTERN.match(sanitized):
            raise ApiValidationError(f"{field} contains invalid characters")
        return sanitized

    def validate_initiate_body(
        self,
        *,
        workflow_id: str | None,
        correlation_id: str | None,
        actor: str | None,
    ) -> InitiateWorkflowApiRequest:
        validated_workflow_id = (
            self.validate_workflow_id(workflow_id, field="workflow_id")
            if workflow_id is not None
            else None
        )
        validated_correlation_id = self._sanitize_string(
            correlation_id,
            field="correlation_id",
            max_len=MAX_CORRELATION_ID_LEN,
            allow_empty=False,
        )
        validated_actor = self._sanitize_string(
            actor,
            field="actor",
            max_len=MAX_ACTOR_LEN,
            allow_empty=False,
        )
        return InitiateWorkflowApiRequest(
            workflow_id=validated_workflow_id,
            correlation_id=validated_correlation_id,
            actor=validated_actor,
        )

    def validate_approval_body(
        self,
        *,
        action: str,
        actor: str | None,
        idempotency_key: str | None,
        header_idempotency_key: str | None = None,
    ) -> SubmitApprovalApiRequest:
        try:
            parsed_action = ApprovalAction(action)
        except ValueError as exc:
            raise ApiValidationError("action must be a valid ApprovalAction") from exc

        validated_actor = self._sanitize_string(
            actor,
            field="actor",
            max_len=MAX_ACTOR_LEN,
            allow_empty=False,
        )
        body_key = self._sanitize_string(
            idempotency_key,
            field="idempotency_key",
            max_len=MAX_IDEMPOTENCY_KEY_LEN,
            allow_empty=False,
        )
        header_key = self.validate_idempotency_header(header_idempotency_key)
        resolved_key = body_key if body_key is not None else header_key

        return SubmitApprovalApiRequest(
            action=parsed_action,
            actor=validated_actor,
            idempotency_key=resolved_key,
        )

    def validate_idempotency_header(self, raw: str | None) -> str | None:
        return self._sanitize_string(
            raw,
            field="idempotency_key",
            max_len=MAX_IDEMPOTENCY_KEY_LEN,
            allow_empty=False,
        )

    @staticmethod
    def _sanitize_string(
        value: str | None,
        *,
        field: str,
        max_len: int,
        allow_empty: bool = False,
    ) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped and not allow_empty:
            raise ApiValidationError(f"{field} must not be empty")
        if not stripped:
            return stripped if allow_empty else None
        if len(stripped) > max_len:
            raise ApiValidationError(f"{field} exceeds maximum length")
        if "\x00" in stripped:
            raise ApiValidationError(f"{field} contains invalid characters")
        for char in stripped:
            code = ord(char)
            if code < 32 or code > 126:
                raise ApiValidationError(f"{field} contains invalid characters")
        return stripped
