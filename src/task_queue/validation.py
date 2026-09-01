"""Pure task envelope validation (LLD §3.1)."""

# GUARDRAIL: Input — reject malformed queue messages at dequeue boundary before handler runs.

from __future__ import annotations

from datetime import datetime, timezone

from config.types import TaskType

from .errors import InvalidTaskMessageError
from .types import TaskMessage


class MessageValidator:
    REQUIRED_FIELDS: tuple[str, ...] = (
        "task_id",
        "workflow_id",
        "task_type",
        "attempt",
        "created_at",
        "payload_reference",
    )

    def validate(self, message: TaskMessage) -> None:
        """Check all field rules; raise InvalidTaskMessageError with missing_fields."""
        missing: list[str] = []

        for field_name in ("task_id", "workflow_id", "payload_reference"):
            if self._non_empty(getattr(message, field_name), field_name) is None:
                missing.append(field_name)

        if message.attempt < 1:
            missing.append("attempt")

        if message.created_at.tzinfo is None:
            missing.append("created_at")

        if missing:
            raise self._error(missing)

    def validate_decoded(
        self,
        *,
        task_id: str | None,
        workflow_id: str | None,
        task_type_raw: str | None,
        attempt_raw: str | None,
        created_at_raw: str | None,
        payload_reference: str | None,
    ) -> TaskMessage:
        """Validate raw decoded strings; never return a partial TaskMessage."""
        missing: list[str] = []

        parsed_task_id = self._non_empty(task_id, "task_id")
        if parsed_task_id is None:
            missing.append("task_id")

        parsed_workflow_id = self._non_empty(workflow_id, "workflow_id")
        if parsed_workflow_id is None:
            missing.append("workflow_id")

        parsed_payload_reference = self._non_empty(
            payload_reference,
            "payload_reference",
        )
        if parsed_payload_reference is None:
            missing.append("payload_reference")

        parsed_task_type: TaskType | None = None
        if task_type_raw is None or not task_type_raw.strip():
            missing.append("task_type")
        else:
            try:
                parsed_task_type = TaskType(task_type_raw.strip())
            except ValueError:
                missing.append("task_type")

        parsed_attempt: int | None = None
        if attempt_raw is None or not attempt_raw.strip():
            missing.append("attempt")
        else:
            try:
                attempt_value = int(attempt_raw.strip())
                if attempt_value < 1:
                    missing.append("attempt")
                else:
                    parsed_attempt = attempt_value
            except ValueError:
                missing.append("attempt")

        parsed_created_at: datetime | None = None
        if created_at_raw is None or not created_at_raw.strip():
            missing.append("created_at")
        else:
            parsed_created_at = self._parse_created_at(created_at_raw)
            if parsed_created_at is None:
                missing.append("created_at")

        if missing:
            raise self._error(missing)

        return TaskMessage(
            task_id=parsed_task_id,  # type: ignore[arg-type]
            workflow_id=parsed_workflow_id,  # type: ignore[arg-type]
            task_type=parsed_task_type,  # type: ignore[arg-type]
            attempt=parsed_attempt,  # type: ignore[arg-type]
            created_at=parsed_created_at,  # type: ignore[arg-type]
            payload_reference=parsed_payload_reference,  # type: ignore[arg-type]
        )

    def _non_empty(self, value: str | None, field_name: str) -> str | None:
        """Strip-aware non-empty check; empty/whitespace → missing."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    def _parse_created_at(self, raw: str) -> datetime | None:
        try:
            normalized = raw.strip().replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)

    def _error(self, missing: list[str]) -> InvalidTaskMessageError:
        fields = ", ".join(missing) if missing else "unknown"
        return InvalidTaskMessageError(
            f"Invalid task message: missing or invalid fields: {fields}",
            missing_fields=tuple(missing),
        )
