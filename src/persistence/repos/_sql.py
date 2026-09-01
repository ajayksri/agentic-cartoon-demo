"""Parameterized SQL fragment constants for persistence repositories."""

from __future__ import annotations

WORKFLOWS = """
SELECT workflow_id, state, state_version, revision_count, failure_reason,
       created_at, updated_at
FROM workflows
WHERE workflow_id = %s
"""

WORKFLOW_TRANSITIONS = """
INSERT INTO workflow_transitions (
    transition_id, workflow_id, from_state, to_state, reason, actor, occurred_at
) VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

TASK_PAYLOADS = """
INSERT INTO task_payloads (ref_id, payload, created_at)
VALUES (%s, %s, %s)
"""

TASKS = """
INSERT INTO tasks (
    task_id, workflow_id, task_type, status, attempt,
    payload_ref_id, payload_ref_kind, idempotency_key,
    failure_reason, created_at, updated_at, completed_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

ARTIFACTS = """
INSERT INTO artifacts (
    artifact_id, workflow_id, artifact_type, name, version,
    logical_version, is_active, content_hash, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

ARTIFACT_CONTENT = """
INSERT INTO artifact_content (artifact_id, content, created_at)
VALUES (%s, %s, %s)
"""

IDEMPOTENCY = """
INSERT INTO idempotency (
    idempotency_key, workflow_id, task_id, result_artifact_id, completed_at
) VALUES (%s, %s, %s, %s, %s)
"""

IDEMPOTENCY_TRY_INSERT = """
INSERT INTO idempotency (
    idempotency_key, workflow_id, task_id, result_artifact_id, completed_at
) VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING idempotency_key, workflow_id, task_id, result_artifact_id, completed_at
"""

OUTBOX = """
INSERT INTO outbox (
    outbox_id, workflow_id, task_id, task_type,
    payload_ref_id, payload_ref_kind, idempotency_key,
    status, created_at, published_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

TASK_LEASES = """
INSERT INTO task_leases (lease_id, task_id, worker_id, acquired_at, expires_at)
VALUES (%s, %s, %s, %s, %s)
"""

AI_INVOCATIONS = """
INSERT INTO ai_invocations (
    invocation_id, workflow_id, task_id, agent_name, agent_version,
    prompt_version, provider, model, input_artifact_id, output_artifact_id,
    attempt, started_at, completed_at, status,
    input_tokens, output_tokens, estimated_cost_usd
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""
