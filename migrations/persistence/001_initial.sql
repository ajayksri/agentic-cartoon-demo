-- Persistence module initial schema (LLD §4.2)

CREATE TABLE workflows (
    workflow_id         TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    state_version       INTEGER NOT NULL DEFAULT 1,
    revision_count      INTEGER NOT NULL DEFAULT 0,
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL
);

CREATE TABLE workflow_transitions (
    id                  BIGSERIAL PRIMARY KEY,
    transition_id       TEXT NOT NULL UNIQUE,
    workflow_id         TEXT NOT NULL REFERENCES workflows(workflow_id),
    from_state          TEXT NOT NULL,
    to_state            TEXT NOT NULL,
    reason              TEXT NOT NULL,
    actor               TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_workflow_transitions_workflow_occurred
    ON workflow_transitions (workflow_id, occurred_at ASC, id ASC);

CREATE TABLE task_payloads (
    ref_id              TEXT PRIMARY KEY,
    payload             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    task_id             TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL REFERENCES workflows(workflow_id),
    task_type           TEXT NOT NULL,
    status              TEXT NOT NULL,
    attempt             INTEGER NOT NULL,
    payload_ref_id      TEXT NOT NULL,
    payload_ref_kind    TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL,
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    CONSTRAINT fk_task_payload
        FOREIGN KEY (payload_ref_id) REFERENCES task_payloads(ref_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX idx_tasks_workflow ON tasks (workflow_id);

CREATE TABLE artifacts (
    artifact_id         TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL REFERENCES workflows(workflow_id),
    artifact_type       TEXT NOT NULL,
    name                TEXT NOT NULL,
    version             INTEGER NOT NULL,
    logical_version     INTEGER NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    content_hash        TEXT,
    created_at          TIMESTAMPTZ NOT NULL,
    UNIQUE (workflow_id, artifact_type, version)
);
CREATE UNIQUE INDEX idx_artifacts_one_active
    ON artifacts (workflow_id, artifact_type)
    WHERE is_active = TRUE;

CREATE TABLE artifact_content (
    artifact_id         TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
    content             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE idempotency (
    idempotency_key     TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    result_artifact_id  TEXT,
    completed_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE outbox (
    outbox_id           TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    task_type           TEXT NOT NULL,
    payload_ref_id      TEXT NOT NULL,
    payload_ref_kind    TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'PENDING',
    created_at          TIMESTAMPTZ NOT NULL,
    published_at        TIMESTAMPTZ
);
CREATE INDEX idx_outbox_pending_created
    ON outbox (created_at ASC)
    WHERE status = 'PENDING';

CREATE TABLE task_leases (
    lease_id            TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL,
    worker_id           TEXT NOT NULL,
    acquired_at         TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX idx_task_leases_task_id ON task_leases (task_id);

CREATE TABLE ai_invocations (
    invocation_id       TEXT PRIMARY KEY,
    workflow_id         TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    agent_name          TEXT NOT NULL,
    agent_version       TEXT NOT NULL,
    prompt_version      TEXT NOT NULL,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_artifact_id   TEXT,
    output_artifact_id  TEXT,
    attempt             INTEGER NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    estimated_cost_usd  NUMERIC(12, 6)
);
CREATE INDEX idx_ai_invocations_workflow ON ai_invocations (workflow_id, started_at ASC);
CREATE INDEX idx_ai_invocations_task ON ai_invocations (task_id) WHERE task_id IS NOT NULL;
