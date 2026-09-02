"""Pure CLI boundary validation before ApiClient invocation."""

from __future__ import annotations

from api.types import InitiateWorkflowApiRequest

from .constants import (
    MAX_ACTOR_LEN,
    MAX_CORRELATION_ID_LEN,
    MAX_WORKFLOW_ID_LEN,
    WORKFLOW_ID_PATTERN,
)
from .errors import CliUsageError

_VALID_APPROVAL_ACTIONS = frozenset({"APPROVE", "REJECT", "REQUEST_REGENERATION"})


class InputValidator:
    """Validates CLI inputs before ApiClient invocation (MOD-CLI-INV-006)."""

    def validate_workflow_id(self, raw: str | None, *, required: bool = True) -> str:
        if raw is None:
            if required:
                raise CliUsageError("workflow_id is required")
            return ""
        stripped = raw.strip()
        if required and not stripped:
            raise CliUsageError("workflow_id must not be empty")
        if len(stripped) > MAX_WORKFLOW_ID_LEN:
            raise CliUsageError(
                f"workflow_id exceeds maximum length of {MAX_WORKFLOW_ID_LEN}"
            )
        if stripped and not WORKFLOW_ID_PATTERN.match(stripped):
            raise CliUsageError("workflow_id contains invalid characters")
        return stripped

    def validate_initiate_fields(
        self,
        *,
        workflow_id: str | None,
        correlation_id: str | None,
        actor: str | None,
    ) -> InitiateWorkflowApiRequest:
        validated_workflow_id = None
        if workflow_id is not None:
            validated_workflow_id = self.validate_workflow_id(workflow_id, required=True)
        validated_correlation_id = self._sanitize_printable_ascii(
            correlation_id,
            field="correlation_id",
            max_len=MAX_CORRELATION_ID_LEN,
            required=False,
        )
        validated_actor = self._sanitize_printable_ascii(
            actor,
            field="actor",
            max_len=MAX_ACTOR_LEN,
            required=False,
        )
        if not any((validated_workflow_id, validated_correlation_id, validated_actor)):
            raise CliUsageError(
                "initiate requires at least one of --workflow-id, --correlation-id, or --actor"
            )
        return InitiateWorkflowApiRequest(
            workflow_id=validated_workflow_id,
            correlation_id=validated_correlation_id,
            actor=validated_actor,
        )

    def validate_approval_action(self, raw: str | None) -> str:
        if raw is None:
            raise CliUsageError("action is required")
        token = raw.strip().upper()
        if token not in _VALID_APPROVAL_ACTIONS:
            raise CliUsageError(f"Unknown approval action: {raw.strip()}")
        return token

    def validate_actor(self, raw: str | None, *, required: bool = False) -> str | None:
        return self._sanitize_printable_ascii(
            raw,
            field="actor",
            max_len=MAX_ACTOR_LEN,
            required=required,
        )

    @staticmethod
    def _sanitize_printable_ascii(
        value: str | None,
        *,
        field: str,
        max_len: int,
        required: bool = False,
    ) -> str | None:
        if value is None:
            if required:
                raise CliUsageError(f"{field} is required")
            return None
        stripped = value.strip()
        if required and not stripped:
            raise CliUsageError(f"{field} must not be empty")
        if not stripped:
            return None
        if len(stripped) > max_len:
            raise CliUsageError(f"{field} exceeds maximum length of {max_len}")
        for char in stripped:
            code = ord(char)
            if code < 32 or code > 126:
                raise CliUsageError(f"{field} contains invalid characters")
        return stripped
