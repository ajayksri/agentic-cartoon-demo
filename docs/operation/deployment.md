# Deployment Guide — Agentic Cartoon Demonstrator V1

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-09-01  
Gate: D1 — Distribution/deployment documentation  
Related: `docs/architecture/deployment-model.md`, `docs/ops/local-demo.md`, `ACD-OPS-001`, `ACD-OPS-002`

V1 targets **local and demo deployment** on a single host. Kubernetes, multi-region, and HA are out of scope (`docs/requirements/non-goals.md`).

---

## 1. Product surfaces (routing)

Per `docs/source/product-surface-profile.yaml`:

| Surface | V1 delivery |
| --- | --- |
| REST API | `cartoon-demo-api` on port 8000 (default) |
| Operator CLI | `cartoon-demo-cli` (HTTP client to API) |
| Operator runtime | `cartoon-demo-coordinator`, `cartoon-demo-worker` |
| Configuration | YAML + environment variables |
| File/artifact outputs | Workflow output package via API/CLI |

Not applicable: graphical UI, gRPC, external library SDK, external event/message API.

---

## 2. Prerequisites

| Requirement | Version / notes |
| --- | --- |
| Python | 3.11+ (`pyproject.toml` → `requires-python`) |
| PostgreSQL | 14+ (Compose image or Homebrew) |
| Redis | 7+ with Streams support |
| Docker Compose | v2 for infra stack (optional if Postgres/Redis run natively) |
| Network | Hacker News API reachable during COLLECT stage |

---

## 3. Install

From repository root:

```bash
pip install -e ".[dev]"
```

This installs package **`agentic-cartoon-demo`** (`pyproject.toml`) and console scripts:

| Script | Role |
| --- | --- |
| `cartoon-demo-api` | HTTP API process |
| `cartoon-demo-coordinator` | Outbox publisher + reconciliation |
| `cartoon-demo-worker` | Task consumer (`--role` or `CARTOON_DEMO_WORKER_ROLE`) |
| `cartoon-demo-cli` | Operator CLI (short-lived) |

Verify install:

```bash
which cartoon-demo-api cartoon-demo-coordinator cartoon-demo-worker cartoon-demo-cli
```

---

## 4. Infrastructure

### Option A — Docker Compose (recommended)

```bash
docker compose -f tests/integration/support/docker-compose.yml up -d
docker compose -f tests/integration/support/docker-compose.yml ps
```

Default DSNs (see `.env.example`):

- PostgreSQL: `postgresql://postgres:postgres@localhost:5432/cartoon`
- Redis: `redis://localhost:6379/0`

### Option B — Native services

Homebrew PostgreSQL 14 + Redis (or equivalent) on the same endpoints as above.

---

## 5. Database schema

Apply once per environment:

```bash
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/cartoon}"
psql "$DATABASE_URL" -f migrations/persistence/001_initial.sql
```

Authority: `migrations/persistence/001_initial.sql` — do not invent DDL.

---

## 6. Configuration bootstrap

```bash
cp .env.example .env
mkdir -p config
cp config/cartoon.demo.yaml config/cartoon.yaml
set -a && source .env && set +a
export CARTOON_CONFIG_PATH="${CARTOON_CONFIG_PATH:-$(pwd)/config/cartoon.yaml}"
```

Fake-provider demo requires `FAKE_API_KEY` only (no paid LLM keys). See `docs/operations/configuration.md`.

---

## 7. Start application processes

Run from repository root with shared `.env` in **separate terminals**:

```bash
# 1. Coordinator
cartoon-demo-coordinator

# 2. Workers (all four roles for full pipeline)
cartoon-demo-worker --role COLLECT
cartoon-demo-worker --role SELECT_TOPIC
cartoon-demo-worker --role GENERATE_SCENARIO
cartoon-demo-worker --role REVIEW_SCENARIO

# 3. API
cartoon-demo-api
```

Readiness:

```bash
curl -s http://127.0.0.1:8000/ready | python3 -m json.tool
```

Expected: HTTP 200, `"status": "ready"`, postgres and redis checks `"ok"`.

---

## 8. Smoke workflow

```bash
curl -s -X POST http://127.0.0.1:8000/workflows \
  -H 'Content-Type: application/json' \
  -d '{"actor":"deploy-smoke"}' | python3 -m json.tool
```

Poll until `AWAITING_HUMAN_APPROVAL` (requires all four workers). See `docs/operations/runbook.md`.

---

## 9. Shutdown

1. Stop API, workers, coordinator (`Ctrl+C` — graceful shutdown).
2. Optional: `docker compose -f tests/integration/support/docker-compose.yml down`

---

## 10. Related documents

| Document | Purpose |
| --- | --- |
| `docs/operations/runbook.md` | Day-2 operator procedures |
| `docs/operations/configuration.md` | Config and env reference |
| `docs/operations/troubleshooting.md` | Common failures |
| `docs/ops/local-demo.md` | Copy-paste demo path (PD-001) |

D1 smoke evidence: `docs/release/d1-smoke-results.md`
