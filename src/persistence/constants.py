"""Module constants — lease TTL defaults and idempotency key documentation."""

from __future__ import annotations

DEFAULT_LEASE_TTL_SECONDS: float = 60.0
RECOMMENDED_LEASE_RENEW_INTERVAL_SECONDS: float = 30.0
IDEMPOTENCY_KEY_FORMAT_DOC = "{workflow_id}:{task_type}:{logical_version}"
TASK_PAYLOAD_REF_KIND: str = "task_payload"
