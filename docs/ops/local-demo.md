# Local Demo Runbook (V1)

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-08-31  
Authority: `docs/decisions/product-decisions.md` PD-001; `docs/architecture/deployment-model.md`  
Related: `ACD-OPS-001`, `ACD-OPS-010`, `ACD-NFR-011`

Short, copy-pasteable steps to run the **fake-provider** local demo on one host.
Infra in Docker; application processes in your Python venv.

---

## Prerequisites

1. **Python 3.11+** and repository checkout.
2. **Docker** (Compose v2) for PostgreSQL + Redis.
3. **Install package** (from repository root):

```bash
pip install -e ".[dev]"
```

4. **Worker production factory (WKR-018):** `cartoon-demo-worker` uses
   `worker.create_production_worker_dependencies` (exported as of WKR-018).
   Ensure `pip install -e ".[dev]"` is current so the factory is on the public surface.

---

## 1. Start infrastructure (PostgreSQL + Redis)

Uses the integration harness Compose file (`ACD-OPS-001`):

```bash
docker compose -f tests/integration/support/docker-compose.yml up -d
```

Wait until healthchecks pass:

```bash
docker compose -f tests/integration/support/docker-compose.yml ps
```

Default endpoints (also in `.env.example`):

| Service | URL |
| --- | --- |
| PostgreSQL | `postgresql://postgres:postgres@localhost:5432/cartoon` |
| Redis | `redis://localhost:6379/0` |

---

## 2. Apply persistence schema

Authority: `migrations/persistence/001_initial.sql` (do not invent DDL).

```bash
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/cartoon}"
psql "$DATABASE_URL" -f migrations/persistence/001_initial.sql
```

To reset an existing database (drops all persistence tables — **destructive**):

```bash
psql "$DATABASE_URL" -f migrations/persistence/000_cleanup.sql
psql "$DATABASE_URL" -f migrations/persistence/001_initial.sql
```

Verify (optional):

```bash
psql "$DATABASE_URL" -c "SELECT to_regclass('public.workflows');"
```

---

## 3. Configure environment (fake provider demo)

Copy the example env file and edit if needed:

```bash
cp .env.example .env
set -a && source .env && set +a
```

**Required for all processes:**

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL DSN |
| `REDIS_URL` | Redis DSN |
| `CARTOON_CONFIG_PATH` | Path to YAML config (see §4) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Must match `DATABASE_URL` credentials |
| `FAKE_API_KEY` | Placeholder for fake provider (`ACD-NFR-011`) |

Paid LLM API keys are **not** required when all agents use provider `fake`.

---

## 4. Application config (fake provider)

Default loader path: `config/cartoon.yaml` (override with `CARTOON_CONFIG_PATH`).

Copy the checked-in demo template:

```bash
mkdir -p config
cp config/cartoon.demo.yaml config/cartoon.yaml
export CARTOON_CONFIG_PATH="${CARTOON_CONFIG_PATH:-$(pwd)/config/cartoon.yaml}"
```

The template sets:

- All agents (`topic_selector`, `scenario_generator`, `critic`) → provider **`fake`**
- Prompt files under `tests/fixtures/agents/prompts/` (repo-relative paths)
- Infrastructure hosts from localhost Compose defaults

Every long-running process calls `config.load_config()` at startup and **fails fast**
on invalid config (`ACD-OPS-010`).

---

## 5. Start application processes

Run each command in a **separate terminal** from the repository root with the same
`.env` loaded. Recommended order (`docs/integration/composition.md` §6):

### 5.1 Coordinator (outbox + reconciliation)

```bash
cartoon-demo-coordinator
```

### 5.2 Workers (one OS process per TaskType stream)

V1 maps one `TaskType` per worker process. For the full COLLECT → … → REVIEW pipeline,
start **four** workers:

```bash
cartoon-demo-worker --role COLLECT
cartoon-demo-worker --role SELECT_TOPIC
cartoon-demo-worker --role GENERATE_SCENARIO
cartoon-demo-worker --role REVIEW_SCENARIO
```

Alternative: `export CARTOON_DEMO_WORKER_ROLE=COLLECT` then `cartoon-demo-worker`.

Default role when omitted: `COLLECT` (single-stream smoke only).

### 5.3 API (HTTP on port 8000)

```bash
cartoon-demo-api
```

Readiness (requires DB + Redis):

```bash
curl -s http://127.0.0.1:8000/ready | python3 -m json.tool
```

---

## 6. Initiate a workflow

### HTTP (recommended)

```bash
curl -s -X POST http://127.0.0.1:8000/workflows \
  -H 'Content-Type: application/json' \
  -d '{"actor":"local-demo"}' | python3 -m json.tool
```

Save `workflow_id` from the response, then poll status:

```bash
export WORKFLOW_ID="<workflow_id_from_response>"
curl -s "http://127.0.0.1:8000/workflows/${WORKFLOW_ID}" | python3 -m json.tool
```

### CLI

```bash
cartoon-demo-cli initiate --actor local-demo
cartoon-demo-cli status --workflow-id "<workflow_id>"
```

Requires API running. Default API URL: `http://127.0.0.1:8000` (override with `CARTOON_API_URL` or `--api-url`).

---

## 7. Expected outcome

With infra up, schema applied, fake provider config, coordinator + **all four** workers,
and API running:

1. POST `/workflows` returns **201** with a `workflow_id`.
2. Coordinator publishes outbox rows → Redis Streams.
3. Workers dequeue by stage (COLLECT → SELECT_TOPIC → GENERATE_SCENARIO → REVIEW_SCENARIO).
4. Terminal wait state for Scenario A: **`AWAITING_HUMAN_APPROVAL`**.

```bash
curl -s "http://127.0.0.1:8000/workflows/${WORKFLOW_ID}" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['state'])"
```

Submit approval (optional):

```bash
curl -s -X POST "http://127.0.0.1:8000/workflows/${WORKFLOW_ID}/approval" \
  -H 'Content-Type: application/json' \
  -d '{"action":"approve","actor":"local-demo"}' | python3 -m json.tool
```

---

## 8. Shutdown

1. Stop API / workers / coordinator (`Ctrl+C` — graceful shutdown per `CG-RT-012`).
2. Stop infra:

```bash
docker compose -f tests/integration/support/docker-compose.yml down
```

---

## 9. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `DependencyWiringError: worker.create_production_worker_dependencies unavailable` | Stale install — run `pip install -e ".[dev]"` from repo root |
| `GET /ready` not OK | Postgres/Redis down or schema not applied |
| `ConfigLoadError` / credential errors | Missing `FAKE_API_KEY`, `POSTGRES_*`, or bad `CARTOON_CONFIG_PATH` |
| Workflow stuck early | Only one worker role running — start all four TaskTypes |
| HN fetch failures during COLLECT | Network required for Hacker News API (collector); not an LLM call |

---

## 10. Related assets

| Asset | Path |
| --- | --- |
| Compose (Postgres + Redis) | `tests/integration/support/docker-compose.yml` |
| Schema migration | `migrations/persistence/001_initial.sql` |
| Demo config template | `config/cartoon.demo.yaml` |
| Env template | `.env.example` |
| Console scripts | `pyproject.toml` → `cartoon-demo-{api,coordinator,worker}` |
| Integration harness env helpers | `tests/integration/helpers.py` |

Run **INT-006** subprocess E2E for automated proof of this path.
