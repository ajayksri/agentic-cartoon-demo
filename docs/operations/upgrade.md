# Upgrade Guide — Agentic Cartoon Demonstrator V1

Status: Approved  
Owner: Human product owner  
Last reviewed: 2026-09-01  
Related: `docs/operations/deployment.md`, `docs/operations/rollback.md`

---

## 1. Scope

V1 upgrades cover:

- Python package `agentic-cartoon-demo` (editable or wheel install)
- Database schema (`migrations/persistence/`)
- Configuration templates

There is **one** published migration file for V1: `migrations/persistence/001_initial.sql`. Future migrations must be applied in order when added.

---

## 2. Pre-upgrade checklist

1. Backup PostgreSQL (`docs/operations/backup-recovery.md`).
2. Stop API, workers, coordinator.
3. Note current git tag/commit or package version.

---

## 3. Application upgrade

From repository root:

```bash
git pull   # if using git checkout
pip install -e ".[dev]"
```

Verify console scripts:

```bash
cartoon-demo-api --help 2>&1 | head -1 || true
which cartoon-demo-cli
```

(Process entry points do not expose `--help`; confirm scripts exist on PATH.)

---

## 4. Schema upgrade

When new migration files appear under `migrations/persistence/`:

```bash
psql "$DATABASE_URL" -f migrations/persistence/00N_description.sql
```

**V1 baseline:** `000_cleanup.sql` + `001_initial.sql`. Re-applying `001_initial.sql` on a populated DB fails with "relation already exists"; for local reset run cleanup first. Production-like environments should use backup/restore instead of cleanup.

---

## 5. Configuration upgrade

1. Diff new `config/cartoon.demo.yaml` against your `config/cartoon.yaml`.
2. Merge new required fields; preserve env-based secrets.
3. Run config validation by starting coordinator — fails fast on invalid YAML.

---

## 6. Post-upgrade smoke

```bash
curl -s http://127.0.0.1:8000/ready
python3 -m pytest tests/integration/test_scenario_a_normal.py -q
```

Or full suite: `tests/integration/ -q`

---

## 7. Compatibility

Technology constraints: `docs/requirements/compatibility.md`. Python **3.11+** required.
