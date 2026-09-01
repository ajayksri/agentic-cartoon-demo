-- Persistence V1 cleanup — drops all objects created by 001_initial.sql.
--
-- DESTRUCTIVE: removes all workflow/task/artifact/outbox data.
-- Intended for local/dev reset when re-applying the baseline schema.
--
-- Usage:
--   psql "$DATABASE_URL" -f migrations/persistence/000_cleanup.sql
--   psql "$DATABASE_URL" -f migrations/persistence/001_initial.sql

DROP TABLE IF EXISTS ai_invocations CASCADE;
DROP TABLE IF EXISTS task_leases CASCADE;
DROP TABLE IF EXISTS outbox CASCADE;
DROP TABLE IF EXISTS idempotency CASCADE;
DROP TABLE IF EXISTS artifact_content CASCADE;
DROP TABLE IF EXISTS artifacts CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS workflow_transitions CASCADE;
DROP TABLE IF EXISTS task_payloads CASCADE;
DROP TABLE IF EXISTS workflows CASCADE;
