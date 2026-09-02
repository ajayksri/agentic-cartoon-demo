"""Unit tests for CLI parser."""

from __future__ import annotations

import pytest

from cli.errors import CliUsageError
from cli.parser import ArgumentParser, FailureInjectionFlagParser
from cli.types import SubcommandId, SubcommandRegistry, SubcommandSpec


def _registry() -> SubcommandRegistry:
    specs = {
        SubcommandId.INITIATE: SubcommandSpec(
            id=SubcommandId.INITIATE,
            name="initiate",
            description="Initiate",
        ),
        SubcommandId.STATUS: SubcommandSpec(
            id=SubcommandId.STATUS,
            name="status",
            description="Status",
        ),
    }
    return SubcommandRegistry(specs=specs, handlers={})


def _parser() -> ArgumentParser:
    return ArgumentParser(registry=_registry())


def test_parse_initiate_with_actor() -> None:
    parsed = _parser().parse(["initiate", "--actor", "ops"])
    assert parsed.subcommand_id == SubcommandId.INITIATE
    assert parsed.initiate_request is not None
    assert parsed.initiate_request.actor == "ops"


def test_parse_status_workflow_id() -> None:
    parsed = _parser().parse(["status", "wf-123"])
    assert parsed.subcommand_id == SubcommandId.STATUS
    assert parsed.workflow_id == "wf-123"


def test_parse_status_with_workflow_id_flag() -> None:
    parsed = _parser().parse(["status", "--workflow-id", "wf-123"])
    assert parsed.subcommand_id == SubcommandId.STATUS
    assert parsed.workflow_id == "wf-123"


def test_parse_resolves_subcommand_from_registry_specs() -> None:
    registry = _registry()
    parsed = ArgumentParser(registry=registry).parse(["status", "wf-1"])
    assert parsed.subcommand_id == SubcommandId.STATUS
    assert registry.get_spec(SubcommandId.STATUS).name == "status"


def test_parse_rejects_unknown_subcommand_not_in_registry() -> None:
    with pytest.raises(CliUsageError, match="Unknown subcommand"):
        _parser().parse(["missing", "wf-1"])


def test_parse_rejects_bare_initiate() -> None:
    with pytest.raises(CliUsageError):
        _parser().parse(["initiate"])


def test_parse_rejects_json_output() -> None:
    with pytest.raises(CliUsageError, match="unsupported output format"):
        _parser().parse(["--output", "json", "status", "wf-1"])


def test_injection_parser_valid_id() -> None:
    override = FailureInjectionFlagParser().extract(["--inject", "FINJ-WKR-PRE"])
    assert override is not None
    assert override.enabled is True
