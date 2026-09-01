# Module Agent Instructions — Configuration (`config`)

Status: Active
Owner: Human product owner
Registry: docs/architecture/modules.yaml

## Purpose

Routing and ownership stub only. Do not infer behavior beyond the approved registry entry.

**Responsibility:** Load, validate, and expose application configuration and credential references.

## Paths

| Kind | Path |
| --- | --- |
| Source | `src/config` |
| Docs | `docs/modules/config` |
| Unit tests | `tests/unit/config` |
| Contract tests | `tests/contract/config` |
| Tasks | `.agents/tasks/config/` |
| Reviews | `.agents/reviews/config/` |

## Dependencies

| Allowed (`depends_on`) | Forbidden |
| --- | --- |
| — | persistence, workflow, worker, agents, api, task_queue |

Composition root: No
Standalone tooling: No
Risk class: Green

## Context policy

- **L1:** This file, module contract packet (when approved), registry entry, assigned task.
- **L2:** Public interfaces of direct dependencies only.
- Do not load other module internals when a public interface exists.

## Non-goals

- Secret storage or rotation
- Runtime config hot-reload

## Authority

Requirements owned by this module are listed in `docs/architecture/modules.yaml` under `owned_requirements` for `config`.
Contract phase (M1) publishes authoritative public behavior under `docs/modules/config/`.

## Test commands

From repository root (after `pip install -e ".[dev]"`):

| Command | Purpose |
| --- | --- |
| `pytest tests/unit/config/ -v` | Unit tests |
| `pytest tests/contract/config/ -v` | Contract tests (CFG-TC-*) |
| `pytest tests/unit/config/ tests/contract/config/ -v -m expect_fail` | Pre-code molds only |
