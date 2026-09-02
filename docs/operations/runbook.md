# Operator Runbook — Agentic Cartoon Demonstrator V1

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-09-01  
Related: `docs/ops/local-demo.md`, `ACD-OPS-005`–`010`

Day-2 operator procedures for the fake-provider local/demo stack.

---

## 1. Start of day

1. Start Postgres + Redis (`docs/operations/deployment.md` §4).
2. Confirm schema applied.
3. Source `.env`; confirm `CARTOON_CONFIG_PATH` points to valid YAML.
4. Start **coordinator → four workers → API** (order matters for first workflow).
5. Verify readiness: `curl -s http://127.0.0.1:8000/ready`

---

## 2. Initiate workflow

### HTTP

```bash
curl -s -X POST http://127.0.0.1:8000/workflows \
  -H 'Content-Type: application/json' \
  -d '{"actor":"operator"}' | python3 -m json.tool
```

### CLI

```bash
export WORKFLOW_ID=$(cartoon-demo-cli initiate --actor operator | awk '/workflow_id:/ {print $2}')
cartoon-demo-cli status --workflow-id "$WORKFLOW_ID"
```

---

## 3. Monitor progression

Poll until `AWAITING_HUMAN_APPROVAL`:

```bash
watch -n2 "cartoon-demo-cli status --workflow-id $WORKFLOW_ID"
```

Or:

```bash
cartoon-demo-cli timeline --workflow-id "$WORKFLOW_ID"
```

**Stuck in early state?** Confirm all four worker roles are running (COLLECT, SELECT_TOPIC, GENERATE_SCENARIO, REVIEW_SCENARIO).

---

## 4. Inspect output package

Approval review (topic, scenario, critic — no source stories):

```bash
cartoon-demo-cli output --workflow-id "$WORKFLOW_ID"
```

Full audit package via API: `GET /workflows/{workflow_id}/output`.

---

## 5. Human approval

```bash
cartoon-demo-cli approve --workflow-id "$WORKFLOW_ID" --action approve --actor operator
```

Valid only in `AWAITING_HUMAN_APPROVAL` (`ACD-SEC-006`).

---

## 6. Failure injection demo

Enable via config or CLI on initiate:

```bash
cartoon-demo-cli initiate --actor operator --inject FINJ-001
```

Exact injection IDs: `docs/modules/failure_injection/contract.md`. Requires `failure_injection.enabled` compatible config.

---

## 7. Graceful shutdown

1. Stop API → workers → coordinator (`Ctrl+C`).
2. Workflows remain durable in PostgreSQL; in-flight tasks may redeliver on restart (`ACD-OPS-003`).

---

## 8. Automated proof

```bash
python3 -m pytest tests/integration/test_subprocess_e2e.py -q
```

Requires live Postgres + Redis.
