# Agentic Cartoon Demonstrator (V1)

Compact agentic AI workflow demonstrator: collect Hacker News stories, select a topic, generate a cartoon scenario, critic review, and human approval — with visible distributed-systems behaviour (retries, idempotency, durable state, observability).

## Distribution

| Item | Value |
| --- | --- |
| Package | `agentic-cartoon-demo` 0.1.0.dev0 |
| Python | 3.11+ |
| Install | `pip install -e ".[dev]"` (from repo root) |

### Console scripts

| Command | Role |
| --- | --- |
| `cartoon-demo-api` | REST API (FastAPI, default port 8000) |
| `cartoon-demo-coordinator` | Outbox publisher + reconciliation |
| `cartoon-demo-worker` | Task worker (`--role COLLECT\|SELECT_TOPIC\|GENERATE_SCENARIO\|REVIEW_SCENARIO`) |
| `cartoon-demo-cli` | Operator CLI (HTTP client) |

## Quick start

1. **Infra:** `docker compose -f tests/integration/support/docker-compose.yml up -d`
2. **Schema:** `psql "$DATABASE_URL" -f migrations/persistence/001_initial.sql` (if tables already exist, run `000_cleanup.sql` first)
3. **Config:** `cp .env.example .env && cp config/cartoon.demo.yaml config/cartoon.yaml`
4. **Install:** `pip install -e ".[dev]"`
5. **Run:** coordinator → four workers → API (see `docs/ops/local-demo.md`)

Verify: `curl -s http://127.0.0.1:8000/ready`

## Documentation

| Topic | Path |
| --- | --- |
| Deployment | `docs/operations/deployment.md` |
| Configuration | `docs/operations/configuration.md` |
| Runbook | `docs/operations/runbook.md` |
| Local demo (short) | `docs/ops/local-demo.md` |
| Architecture | `docs/architecture/system-hld.md` |
| Requirements | `docs/requirements/product.md` |

## Tests

```bash
python3 -m pytest tests/integration/ -q   # requires Postgres + Redis
python3 -m pytest tests/unit/ -q          # module unit tests
```

## License / status

V1 demonstration codebase. See `docs/requirements/non-goals.md` for explicit exclusions.
