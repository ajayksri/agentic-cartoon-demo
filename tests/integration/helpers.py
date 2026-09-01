"""Integration harness helpers (INT-001).

Public-interface helpers only. Do not import the runtime composition internal
bootstrap seam here — that import is allowlisted solely in
``tests/integration/conftest.py``.

Required environment (documented for operators / CI)::

    DATABASE_URL   postgresql://USER:PASSWORD@HOST:PORT/DB
    REDIS_URL      redis://[:PASSWORD@]HOST:PORT/DB

Optional companion env for config credential checks when loading YAML::

    FAKE_API_KEY, POSTGRES_USER, POSTGRES_PASSWORD

Schema authority: ``migrations/persistence/001_initial.sql`` (do not invent DDL).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml

from config import load_config
from config.types import AppConfig, ConfigSource, InjectionId

# ---------------------------------------------------------------------------
# Environment contract (ACD-OPS-001 / integration-test-plan §2.2)
# ---------------------------------------------------------------------------

DATABASE_URL_ENV = "DATABASE_URL"
REDIS_URL_ENV = "REDIS_URL"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/cartoon"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
FAKE_API_KEY_ENV = "FAKE_API_KEY"
DEFAULT_FAKE_API_KEY = "integration-fake-key"
POSTGRES_USER_ENV = "POSTGRES_USER"
POSTGRES_PASSWORD_ENV = "POSTGRES_PASSWORD"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_MIGRATION_PATH = REPO_ROOT / "migrations" / "persistence" / "001_initial.sql"
SUPPORT_COMPOSE_PATH = Path(__file__).resolve().parent / "support" / "docker-compose.yml"
PROMPT_TOPIC = "tests/fixtures/agents/prompts/topic_selector.txt"
PROMPT_SCENARIO = "tests/fixtures/agents/prompts/scenario_generator.txt"
PROMPT_CRITIC = "tests/fixtures/agents/prompts/critic.txt"

_FORBIDDEN_IMPORT_PREFIXES = (
    "runtime.wiring",
    "worker.handlers",
    "agents.",
    "persistence.repositories",
)


@dataclass(frozen=True, slots=True)
class PostgresEndpoint:
    """Parsed ``DATABASE_URL`` components for YAML + psycopg."""

    host: str
    port: int
    database: str
    user: str
    password: str
    dsn: str


@dataclass(frozen=True, slots=True)
class RedisEndpoint:
    """Parsed ``REDIS_URL`` components for YAML + redis clients."""

    host: str
    port: int
    db: int
    password: str | None
    url: str


def get_database_url(*, default: str | None = DEFAULT_DATABASE_URL) -> str:
    """Return ``DATABASE_URL`` or the harness default."""
    return os.environ.get(DATABASE_URL_ENV, default or DEFAULT_DATABASE_URL)


def get_redis_url(*, default: str | None = DEFAULT_REDIS_URL) -> str:
    """Return ``REDIS_URL`` or the harness default."""
    return os.environ.get(REDIS_URL_ENV, default or DEFAULT_REDIS_URL)


def parse_database_url(url: str) -> PostgresEndpoint:
    """Parse a PostgreSQL URL into connection settings."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"DATABASE_URL must use postgresql:// scheme, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("DATABASE_URL missing host")
    database = (parsed.path or "/").lstrip("/") or "postgres"
    user = unquote(parsed.username or "postgres")
    password = unquote(parsed.password or "")
    return PostgresEndpoint(
        host=parsed.hostname,
        port=int(parsed.port or 5432),
        database=database,
        user=user,
        password=password,
        dsn=url,
    )


def parse_redis_url(url: str) -> RedisEndpoint:
    """Parse a Redis URL into connection settings."""
    parsed = urlparse(url)
    if parsed.scheme not in ("redis", "rediss"):
        raise ValueError(f"REDIS_URL must use redis:// scheme, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("REDIS_URL missing host")
    db = int((parsed.path or "/0").lstrip("/") or "0")
    password = unquote(parsed.password) if parsed.password else None
    return RedisEndpoint(
        host=parsed.hostname,
        port=int(parsed.port or 6379),
        db=db,
        password=password,
        url=url,
    )


def postgres_available(url: str | None = None, *, timeout_seconds: float = 1.5) -> bool:
    """Return True when PostgreSQL accepts a connection at ``DATABASE_URL``."""
    dsn = url or get_database_url()
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=max(1, int(timeout_seconds))) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def redis_available(url: str | None = None, *, timeout_seconds: float = 1.5) -> bool:
    """Return True when Redis accepts PING at ``REDIS_URL``."""
    target = url or get_redis_url()
    try:
        import redis

        client = redis.Redis.from_url(target, socket_connect_timeout=timeout_seconds)
        return bool(client.ping())
    except Exception:
        return False


def infra_skip_reason(*, database_url: str | None = None, redis_url: str | None = None) -> str | None:
    """Human-readable skip reason when required infra is absent; None if ready."""
    db_url = database_url or get_database_url()
    r_url = redis_url or get_redis_url()
    missing: list[str] = []
    if not postgres_available(db_url):
        missing.append(
            f"PostgreSQL unavailable at {DATABASE_URL_ENV}={db_url!r} "
            f"(start via docker compose -f {SUPPORT_COMPOSE_PATH})"
        )
    if not redis_available(r_url):
        missing.append(
            f"Redis unavailable at {REDIS_URL_ENV}={r_url!r} "
            f"(start via docker compose -f {SUPPORT_COMPOSE_PATH})"
        )
    if not missing:
        return None
    return "; ".join(missing)


def schema_already_applied(dsn: str) -> bool:
    """True when the persistence ``workflows`` table exists."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT to_regclass('public.workflows')").fetchone()
    return row is not None and row[0] is not None


def apply_persistence_schema(*, database_url: str | None = None) -> Path:
    """Apply approved migration ``001_initial.sql`` once per database.

    Raises FileNotFoundError if the approved migration artifact is missing
    (EXTERNAL_EVIDENCE / ops gap — do not invent DDL).
    """
    if not SCHEMA_MIGRATION_PATH.is_file():
        raise FileNotFoundError(
            f"Approved schema missing at {SCHEMA_MIGRATION_PATH}; "
            "cannot invent production DDL (INT-001 EXTERNAL_EVIDENCE_REQUIRED)"
        )
    dsn = database_url or get_database_url()
    if schema_already_applied(dsn):
        return SCHEMA_MIGRATION_PATH

    import psycopg

    ddl = SCHEMA_MIGRATION_PATH.read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        conn.execute(ddl)
        conn.commit()
    return SCHEMA_MIGRATION_PATH


def ensure_fake_provider_env() -> None:
    """Force fake AI credentials into the process env (ACD-NFR-011 / ACD-INT-005)."""
    os.environ.setdefault(FAKE_API_KEY_ENV, DEFAULT_FAKE_API_KEY)


def sync_postgres_credential_env(endpoint: PostgresEndpoint) -> None:
    """Align POSTGRES_USER/PASSWORD with DATABASE_URL for config credential checks."""
    os.environ[POSTGRES_USER_ENV] = endpoint.user
    os.environ[POSTGRES_PASSWORD_ENV] = endpoint.password


def ensure_subprocess_pythonpath(env: dict[str, str]) -> None:
    """Runtime console entry subprocesses need ``src`` on PYTHONPATH."""
    src_path = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    )


def build_integration_config_dict(
    *,
    postgres: PostgresEndpoint,
    redis: RedisEndpoint,
    failure_injection_enabled: bool = False,
    active_injections: Sequence[str] | Sequence[InjectionId] = (),
    api_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    """Build a fake-provider-only AppConfig YAML tree for integration tests."""
    injection_ids = [str(item) for item in active_injections]
    _ = api_base_url  # harness HTTP concern; not part of AppConfig YAML schema
    return {
        "config_version": "1",
        "infrastructure": {
            "postgres": {
                "host": postgres.host,
                "port": postgres.port,
                "database": postgres.database,
                "user_env": POSTGRES_USER_ENV,
                "password_env": POSTGRES_PASSWORD_ENV,
            },
            "redis": {
                "host": redis.host,
                "port": redis.port,
                "db": redis.db,
                **({"password_env": "REDIS_PASSWORD"} if redis.password else {}),
            },
        },
        "agents": {
            "topic_selector": {
                "provider": "fake",
                "model": "fake-model",
                "prompt_file": PROMPT_TOPIC,
            },
            "scenario_generator": {
                "provider": "fake",
                "model": "fake-model",
                "prompt_file": PROMPT_SCENARIO,
            },
            "critic": {
                "provider": "fake",
                "model": "fake-model",
                "prompt_file": PROMPT_CRITIC,
            },
        },
        "providers": {
            "fake": {
                "api_key_env": FAKE_API_KEY_ENV,
            },
        },
        "collection": {
            "candidate_count": 10,
        },
        "workflow": {
            "max_scenario_revisions": 2,
        },
        "workers": {
            "topic_selector_concurrency": 1,
            "scenario_generator_concurrency": 1,
            "critic_concurrency": 1,
        },
        "retry": {
            "COLLECT": {
                "max_attempts": 3,
                "backoff": {"initial_seconds": 0.1, "multiplier": 2.0, "max_seconds": 1.0},
            },
            "SELECT_TOPIC": {
                "max_attempts": 3,
                "backoff": {"initial_seconds": 0.1, "multiplier": 2.0, "max_seconds": 1.0},
            },
            "GENERATE_SCENARIO": {
                "max_attempts": 3,
                "backoff": {"initial_seconds": 0.1, "multiplier": 2.0, "max_seconds": 1.0},
            },
            "REVIEW_SCENARIO": {
                "max_attempts": 3,
                "backoff": {"initial_seconds": 0.1, "multiplier": 2.0, "max_seconds": 1.0},
            },
        },
        "timeouts": {
            "fake": {"read_seconds": 5.0},
        },
        "failure_injection": {
            "enabled": failure_injection_enabled or bool(injection_ids),
            "active_injections": injection_ids,
        },
    }


def write_temp_config_yaml(
    path: Path,
    *,
    database_url: str | None = None,
    redis_url: str | None = None,
    failure_injection_enabled: bool = False,
    active_injections: Sequence[str] | Sequence[InjectionId] = (),
    api_base_url: str = "http://127.0.0.1:8000",
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write a temporary AppConfig YAML with fake providers + optional FINJ overrides."""
    postgres = parse_database_url(database_url or get_database_url())
    redis = parse_redis_url(redis_url or get_redis_url())
    tree = build_integration_config_dict(
        postgres=postgres,
        redis=redis,
        failure_injection_enabled=failure_injection_enabled,
        active_injections=active_injections,
        api_base_url=api_base_url,
    )
    if extra:
        tree = {**tree, **dict(extra)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(tree, sort_keys=False), encoding="utf-8")
    return path


def failure_injection_overrides(
    *,
    enabled: bool = True,
    active_injections: Sequence[str] | Sequence[InjectionId] = (),
) -> Any:
    """Build a public CLI failure-injection override for merge helpers."""
    from cli import CliFailureInjectionOverride

    return CliFailureInjectionOverride(
        enabled=enabled,
        active_injections=frozenset(str(item) for item in active_injections),
    )


def apply_failure_injection_overrides(
    config: AppConfig,
    *,
    enabled: bool = True,
    active_injections: Sequence[str] | Sequence[InjectionId] = (),
) -> AppConfig:
    """Merge FINJ overrides into an AppConfig via public CLI merge API."""
    from cli import CliConfigOverride, merge_cli_config_override

    override = CliConfigOverride(
        failure_injection=failure_injection_overrides(
            enabled=enabled,
            active_injections=active_injections,
        )
    )
    return merge_cli_config_override(config, override)


def load_integration_app_config(
    config_path: Path,
    *,
    database_url: str | None = None,
    redis_url: str | None = None,
) -> AppConfig:
    """Load AppConfig from a harness YAML after syncing credential env from URLs."""
    ensure_fake_provider_env()
    postgres = parse_database_url(database_url or get_database_url())
    sync_postgres_credential_env(postgres)
    redis = parse_redis_url(redis_url or get_redis_url())
    if redis.password:
        os.environ["REDIS_PASSWORD"] = redis.password
    return load_config(ConfigSource(path=config_path))


def http_client_base_url(*, host: str = "127.0.0.1", port: int = 8000) -> str:
    """HTTP base URL for API integration clients."""
    return f"http://{host}:{port}"


def assert_no_forbidden_imports(module_source: str) -> list[str]:
    """Return forbidden import strings found in source (public-interface rule)."""
    found: list[str] = []
    for prefix in _FORBIDDEN_IMPORT_PREFIXES:
        if prefix in module_source or f"import {prefix.rstrip('.')}" in module_source:
            # Cheap string scan; callers may also AST-scan in later INT tasks.
            if f"{prefix}" in module_source:
                found.append(prefix)
    return found
