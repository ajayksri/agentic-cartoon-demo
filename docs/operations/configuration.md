# Configuration Reference — Agentic Cartoon Demonstrator V1

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-09-01  
Related: `docs/requirements/configuration.md`, `ACD-CFG-*`, `config/cartoon.demo.yaml`, `.env.example`

---

## 1. Principles

- **No secrets in YAML** — API keys via environment variables only (`ACD-CFG-001`, `ACD-SEC-001`).
- **Fail fast** — invalid config prevents process startup (`ACD-CFG-010`, `ACD-OPS-010`).
- **Provider-scoped credentials** — only configured providers require keys (`ACD-SEC-002`).

---

## 2. Environment variables

| Variable | Required | Used by | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes | All processes | PostgreSQL DSN |
| `REDIS_URL` | Yes | All processes | Redis DSN |
| `CARTOON_CONFIG_PATH` | Yes | All processes | Path to YAML config (default `config/cartoon.yaml`) |
| `POSTGRES_USER` | Yes* | Config loader | Credential env referenced by YAML |
| `POSTGRES_PASSWORD` | Yes* | Config loader | Credential env referenced by YAML |
| `FAKE_API_KEY` | Yes (fake demo) | Fake provider | Placeholder when all agents use `fake` |
| `OPENAI_API_KEY` | If OpenAI configured | Provider | Real LLM calls |
| `ANTHROPIC_API_KEY` | If Anthropic configured | Provider | Real LLM calls |
| `GOOGLE_API_KEY` | If Gemini configured | Provider | Real LLM calls |
| `MOONSHOT_API_KEY` | If Kimi configured | Provider | Moonshot/Kimi subscription API key |
| `CARTOON_DEMO_WORKER_ROLE` | No | Worker | Default worker role if `--role` omitted |
| `CARTOON_API_URL` | No | CLI | API base URL (default `http://127.0.0.1:8000`) |
| `CARTOON_CLI_TIMEOUT` | No | CLI | Request timeout seconds |

\*Required when YAML uses `user_env` / `password_env` for Postgres (demo template does).

Template: `.env.example`

---

## 3. Application YAML

Loader: `config.load_config()` at each process startup.

Demo template: `config/cartoon.demo.yaml` → copy to `config/cartoon.yaml`.

| Section | Purpose |
| --- | --- |
| `config_version` | Schema version |
| `infrastructure.postgres` / `redis` | Host/port; credentials via env names |
| `agents.*` | Provider, model, prompt file per agent |
| `providers.*` | Provider-specific settings (`api_key_env`) |
| `collection` | HN candidate count |
| `workflow` | e.g. `max_scenario_revisions` |
| `workers` | Concurrency per agent type |
| `retry` | Per-`TaskType` retry/backoff |
| `timeouts` | Provider read timeouts |
| `failure_injection` | Enabled flag and active injection IDs |

Prompt paths in config are **repo-relative** (`prompts/<agent>/v1.txt`). Run processes from repository root or adjust paths.

---

## 4. CLI flags

Global flags (see `src/cli/constants.py`):

| Flag | Env fallback | Purpose |
| --- | --- | --- |
| `--api-url` | `CARTOON_API_URL` | API base URL |
| `--config-path` | `CARTOON_CONFIG_PATH` | Config for initiate bootstrap |
| `--timeout` | `CARTOON_CLI_TIMEOUT` | HTTP timeout |
| `--inject` | — | Failure injection override (initiate) |

Subcommands: `initiate`, `status`, `history`, `output`, `timeline`, `approve`.

Example:

```bash
cartoon-demo-cli initiate --actor demo-operator
cartoon-demo-cli status --workflow-id <id>
```

---

## 5. Validation errors

| Symptom | Cause |
| --- | --- |
| `ConfigLoadError` | Missing file, bad YAML |
| `ConfigValidationError` | Invalid field values |
| Missing credential at startup | Env var for configured provider not set |

Errors name the failing key where possible (`ACD-CFG-010`).

---

## 6. Failure injection

Configured under `failure_injection` in YAML. CLI `--inject` can override on `initiate` (`ACD-CLI-003`, `ACD-SEC-007`). Not exposed on public HTTP API.

---

## 7. Related

- Security: `docs/operations/security.md`
- Deployment: `docs/operations/deployment.md`
