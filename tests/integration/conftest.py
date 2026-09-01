"""Integration test fixtures (INT-001 / integration-test-plan §2).

Required environment
--------------------
``DATABASE_URL``
    PostgreSQL DSN, e.g. ``postgresql://postgres:postgres@localhost:5432/cartoon``.
``REDIS_URL``
    Redis DSN, e.g. ``redis://localhost:6379/0``.

Local infra (optional Compose under this package)::

    docker compose -f tests/integration/support/docker-compose.yml up -d

Schema
------
Applies approved migration ``migrations/persistence/001_initial.sql`` once per session
when infra is available. Does not invent DDL.

Bootstrap allowlist
-------------------
``runtime.composition._bootstrap_for_tests`` may be imported **only** from this conftest
(LLD §21.3 / interface-gaps §4.1). Scenario modules must use the ``bootstrap_for_tests``
fixture — never import the internal seam directly.

AI providers
------------
Harness forces fake/mock providers (``ACD-NFR-011``, ``ACD-INT-005``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration import helpers as harness


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: Phase 81 composition / E2E integration test",
    )
    config.addinivalue_line(
        "markers",
        "it_int: IT-INT-* catalogue case",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    """Resolved ``DATABASE_URL`` (default local Compose DSN)."""
    return harness.get_database_url()


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Resolved ``REDIS_URL`` (default local Compose DSN)."""
    return harness.get_redis_url()


@pytest.fixture(scope="session")
def integration_infra(database_url: str, redis_url: str) -> dict[str, str]:
    """Require live PostgreSQL + Redis or skip with an explicit reason.

    Tests that need real infra should depend on this fixture. Absence must never
    silently pass (integration-test-plan §2.1 / INT-001).
    """
    reason = harness.infra_skip_reason(database_url=database_url, redis_url=redis_url)
    if reason is not None:
        pytest.skip(reason)
    return {
        harness.DATABASE_URL_ENV: database_url,
        harness.REDIS_URL_ENV: redis_url,
    }


@pytest.fixture(scope="session")
def integration_schema(integration_infra: dict[str, str]) -> Path:
    """Apply approved persistence schema once per session when infra is up."""
    return harness.apply_persistence_schema(
        database_url=integration_infra[harness.DATABASE_URL_ENV]
    )


@pytest.fixture
def temp_app_config_path(
    tmp_path: Path,
    database_url: str,
    redis_url: str,
) -> Path:
    """Write a fake-provider-only AppConfig YAML under a temp directory."""
    harness.ensure_fake_provider_env()
    path = tmp_path / "cartoon.integration.yaml"
    return harness.write_temp_config_yaml(
        path,
        database_url=database_url,
        redis_url=redis_url,
        failure_injection_enabled=False,
        active_injections=(),
        api_base_url=harness.http_client_base_url(),
    )


@pytest.fixture
def integration_app_config(
    temp_app_config_path: Path,
    database_url: str,
    redis_url: str,
) -> Any:
    """Validated ``AppConfig`` loaded from the harness temp YAML (fake providers)."""
    return harness.load_integration_app_config(
        temp_app_config_path,
        database_url=database_url,
        redis_url=redis_url,
    )


@pytest.fixture
def failure_injection_config_factory(
    tmp_path: Path,
    database_url: str,
    redis_url: str,
) -> Callable[..., Any]:
    """Build AppConfig with FINJ overrides via public CLI merge helpers."""

    def _factory(
        *,
        enabled: bool = True,
        active_injections: tuple[str, ...] = (),
    ) -> Any:
        path = tmp_path / f"cartoon.finj.{enabled}.{len(active_injections)}.yaml"
        harness.write_temp_config_yaml(
            path,
            database_url=database_url,
            redis_url=redis_url,
            failure_injection_enabled=enabled,
            active_injections=active_injections,
        )
        base = harness.load_integration_app_config(
            path,
            database_url=database_url,
            redis_url=redis_url,
        )
        if not active_injections and not enabled:
            return base
        return harness.apply_failure_injection_overrides(
            base,
            enabled=enabled,
            active_injections=active_injections,
        )

    return _factory


@pytest.fixture
def http_base_url() -> str:
    """Default HTTP base URL for API clients (override per-test as needed)."""
    return harness.http_client_base_url()


@pytest.fixture
def bootstrap_for_tests() -> Callable[..., Any]:
    """Allowlisted wrapper around ``runtime.composition._bootstrap_for_tests``.

    Import of the internal seam is confined to this fixture body (conftest only).
    """

    def _factory(**kwargs: Any) -> Any:
        from runtime.composition import _bootstrap_for_tests

        if "entry" not in kwargs or "config" not in kwargs:
            raise TypeError(
                "bootstrap_for_tests requires keyword args entry= and config= "
                "(see runtime LLD §21.3)"
            )
        return _bootstrap_for_tests(**kwargs)

    return _factory


@pytest.fixture
def harness_public_interface_guard() -> Iterator[None]:
    """Assert harness modules do not import forbidden internals."""
    import ast

    helpers_path = Path(__file__).parent / "helpers.py"
    helpers_tree = ast.parse(helpers_path.read_text(encoding="utf-8"))
    for node in ast.walk(helpers_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("runtime.composition")
                assert not alias.name.startswith("runtime.wiring")
                assert not alias.name.startswith("worker.handlers")
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("runtime.composition")
            assert not node.module.startswith("runtime.wiring")
            assert not node.module.startswith("worker.handlers")
            if node.module.startswith("runtime"):
                assert node.module == "runtime"  # public package only if ever needed
    conftest_src = Path(__file__).read_text(encoding="utf-8")
    for prefix in ("worker.handlers", "persistence.repositories"):
        assert prefix not in conftest_src
    yield
