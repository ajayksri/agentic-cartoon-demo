"""Production console entry for ``cartoon-demo-cli`` (CG-RT-011)."""

from __future__ import annotations

import os
import sys

from observability import configure_observability, get_logger, get_tracer

from .constants import DEFAULT_API_BASE_URL, ENV_API_URL
from .protocols import CliDependencies
from .registry import build_default_subcommand_registry
from .types import CliClientConfig, SubcommandRegistry


class _CliObservabilitySettings:
    """Minimal observability bootstrap for short-lived CLI processes."""

    service_name = "cartoon-demo-cli"
    log_level = "INFO"


def build_production_cli_dependencies() -> CliDependencies:
    """Wire default CLI dependencies for operator use."""
    configure_observability(_CliObservabilitySettings())
    logger = get_logger()
    tracer = get_tracer()
    api_url = os.environ.get(ENV_API_URL, DEFAULT_API_BASE_URL)
    client_config = CliClientConfig(api_base_url=api_url)
    placeholder = CliDependencies(
        client_config=client_config,
        registry=SubcommandRegistry(specs={}, handlers={}),
        logger=logger,
        tracer=tracer,
    )
    registry = build_default_subcommand_registry(deps=placeholder)
    return CliDependencies(
        client_config=client_config,
        registry=registry,
        logger=logger,
        tracer=tracer,
    )


def main(argv: list[str] | None = None) -> int:
    """Console script entry — parse argv and return process exit code."""
    from .app import run_cli

    deps = build_production_cli_dependencies()
    return run_cli(argv or sys.argv[1:], deps=deps)


def _entry_cli() -> None:
    raise SystemExit(main())
