# Troubleshooting — Agentic Cartoon Demonstrator V1

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-09-01  
Related: `docs/ops/local-demo.md` §9

---

## Symptom index

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `DependencyWiringError` on worker start | Stale install | `pip install -e ".[dev]"` from repo root |
| `GET /ready` returns 503 | Postgres/Redis down or schema missing | Start infra; run `001_initial.sql` |
| `ConfigLoadError` / credential error | Missing env vars | Check `.env`: `FAKE_API_KEY`, `POSTGRES_*`, `CARTOON_CONFIG_PATH` |
| Workflow stuck in `COLLECTING` | Missing COLLECT worker or HN network | Start `cartoon-demo-worker --role COLLECT`; check network |
| Workflow stuck after COLLECT | Missing downstream worker roles | Start SELECT_TOPIC, GENERATE_SCENARIO, REVIEW_SCENARIO workers |
| Workflow stuck in pause state (e.g. `COLLECTED`) | Dispatch bridge / worker issue | Check worker logs; re-run integration Scenario A |
| CLI exit code **2** | Usage error | Provide subcommand: `initiate`, `status`, etc. |
| CLI exit code **3** | Connection/API error | Confirm API running; check `CARTOON_API_URL` |
| CLI exit code **1** | API or business error | Read stderr message; check workflow state |
| `ModuleNotFoundError: runtime` in subprocess tests | PYTHONPATH | Run from repo root after `pip install -e ".[dev]"` |
| Duplicate task side effects | Expected at-least-once delivery | Idempotency should prevent double completion (Scenario C) |
| Approval rejected | Wrong workflow state | Must be `AWAITING_HUMAN_APPROVAL` |

---

## Exit codes (CLI)

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Error (API/business) |
| 2 | Usage |
| 3 | Connection |

Source: `src/cli/types.py` → `CliExitCode`

---

## Logs

All processes emit structured JSON logs to stdout. Search by `workflow_id` when diagnosing a specific run.

---

## Integration test isolation

```bash
python3 -m pytest tests/integration/test_scenario_a_normal.py -q
```

Full suite: `python3 -m pytest tests/integration/ -q` (requires Postgres + Redis).

---

## Escalation

| Class | Route |
| --- | --- |
| Config/product ambiguity | `docs/requirements/open-questions.md` |
| Integration gap | `docs/integration/interface-gaps.md` |
| Security incident | Rotate env credentials; review `docs/operations/security.md` |
