"""Argument parsing and failure-injection flag extraction."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from api.types import InitiateWorkflowApiRequest
from config.types import InjectionId

from .constants import (
    DEFAULT_API_BASE_URL,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ENV_API_URL,
    ENV_CONFIG_PATH,
    ENV_REQUEST_TIMEOUT,
    FLAG_ACTION,
    FLAG_ACTOR,
    FLAG_API_URL,
    FLAG_CONFIG_PATH,
    FLAG_CORRELATION_ID,
    FLAG_INJECT,
    FLAG_OUTPUT,
    FLAG_TIMEOUT,
    FLAG_WORKFLOW_ID,
)
from .errors import CliUsageError
from .types import (
    CliClientConfig,
    CliConfigOverride,
    CliFailureInjectionOverride,
    SubcommandId,
    SubcommandRegistry,
)
from .validation import InputValidator

_GLOBAL_FLAGS_WITH_VALUE = {
    FLAG_API_URL,
    FLAG_CONFIG_PATH,
    FLAG_TIMEOUT,
    FLAG_OUTPUT,
}


@dataclass(frozen=True, slots=True)
class ParsedCliInvocation:
    """Immutable parse result consumed by DefaultCliApp."""

    subcommand_id: SubcommandId
    client_config: CliClientConfig
    config_override: CliConfigOverride | None
    workflow_id: str | None
    initiate_request: InitiateWorkflowApiRequest | None
    approval_action: str | None
    raw_args: tuple[str, ...]


class FailureInjectionFlagParser:
    """Extracts and validates --inject flags from argv."""

    def extract(self, argv: Sequence[str]) -> CliFailureInjectionOverride | None:
        injection_ids: list[str] = []
        index = 0
        while index < len(argv):
            token = argv[index]
            if token == FLAG_INJECT:
                if index + 1 >= len(argv):
                    raise CliUsageError(f"{FLAG_INJECT} requires a value")
                value = argv[index + 1]
                try:
                    InjectionId(value)
                except ValueError as exc:
                    raise CliUsageError(
                        f"Unknown failure injection id: {value}",
                    ) from exc
                injection_ids.append(value)
                index += 2
                continue
            index += 1
        if not injection_ids:
            return None
        return CliFailureInjectionOverride(
            enabled=True,
            active_injections=frozenset(injection_ids),
        )

    def parse_failure_injection_flags(
        self,
        argv: Sequence[str],
    ) -> CliFailureInjectionOverride | None:
        return self.extract(argv)


class ArgumentParser:
    """Parses CLI argv into ParsedCliInvocation."""

    def __init__(
        self,
        *,
        registry: SubcommandRegistry,
        validator: InputValidator | None = None,
        injection_parser: FailureInjectionFlagParser | None = None,
    ) -> None:
        self._registry = registry
        self._validator = validator or InputValidator()
        self._injection_parser = injection_parser or FailureInjectionFlagParser()

    def parse(self, argv: Sequence[str]) -> ParsedCliInvocation:
        injection_override = self._injection_parser.extract(argv)
        global_values, remaining = _parse_global_flags(argv)

        if global_values.get("output") == "json":
            raise CliUsageError("unsupported output format")

        if not remaining:
            raise CliUsageError("subcommand is required")

        subcommand_token = remaining[0]
        subcommand_args = tuple(remaining[1:])
        subcommand_id = _subcommand_id_from_registry(self._registry, subcommand_token)

        api_base_url = (
            global_values.get("api_url")
            or os.environ.get(ENV_API_URL)
            or DEFAULT_API_BASE_URL
        )
        config_path_raw = global_values.get("config_path") or os.environ.get(
            ENV_CONFIG_PATH
        )
        config_path = Path(config_path_raw) if config_path_raw else None
        timeout_raw = global_values.get("timeout") or os.environ.get(ENV_REQUEST_TIMEOUT)
        if timeout_raw is None:
            timeout_seconds = DEFAULT_REQUEST_TIMEOUT_SECONDS
        else:
            try:
                timeout_seconds = float(timeout_raw)
            except (TypeError, ValueError) as exc:
                raise CliUsageError("timeout must be a number") from exc

        client_config = CliClientConfig(
            api_base_url=api_base_url,
            config_path=config_path,
            request_timeout_seconds=timeout_seconds,
        )

        config_override = None
        if injection_override is not None:
            config_override = CliConfigOverride(failure_injection=injection_override)

        workflow_id: str | None = None
        initiate_request: InitiateWorkflowApiRequest | None = None
        approval_action: str | None = None

        if subcommand_id == SubcommandId.INITIATE:
            initiate_args = _parse_initiate_args(subcommand_args)
            initiate_request = self._validator.validate_initiate_fields(
                workflow_id=initiate_args.get("workflow_id"),
                correlation_id=initiate_args.get("correlation_id"),
                actor=initiate_args.get("actor"),
            )
        elif subcommand_id == SubcommandId.APPROVE:
            workflow_id, action_token = _parse_approve_args(subcommand_args)
            workflow_id = self._validator.validate_workflow_id(workflow_id, required=True)
            approval_action = self._validator.validate_approval_action(action_token)
        else:
            if not subcommand_args or len(subcommand_args) != 1:
                raise CliUsageError(f"{subcommand_token} requires a workflow_id argument")
            workflow_id = self._validator.validate_workflow_id(
                subcommand_args[0],
                required=True,
            )

        return ParsedCliInvocation(
            subcommand_id=subcommand_id,
            client_config=client_config,
            config_override=config_override,
            workflow_id=workflow_id,
            initiate_request=initiate_request,
            approval_action=approval_action,
            raw_args=tuple(argv),
        )


def _parse_global_flags(argv: Sequence[str]) -> tuple[dict[str, str], tuple[str, ...]]:
    values: dict[str, str] = {}
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == FLAG_INJECT:
            index += 2
            continue
        if token in _GLOBAL_FLAGS_WITH_VALUE:
            if index + 1 >= len(argv):
                raise CliUsageError(f"{token} requires a value")
            key = token.lstrip("-").replace("-", "_")
            values[key] = argv[index + 1]
            index += 2
            continue
        remaining.append(token)
        index += 1
    return values, tuple(remaining)


def _subcommand_id_from_registry(registry: SubcommandRegistry, token: str) -> SubcommandId:
    for subcommand_id, spec in registry.specs.items():
        if spec.name == token:
            return subcommand_id
    raise CliUsageError(f"Unknown subcommand: {token}")


def _parse_initiate_args(args: Sequence[str]) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "workflow_id": None,
        "correlation_id": None,
        "actor": None,
    }
    index = 0
    while index < len(args):
        token = args[index]
        if token == FLAG_WORKFLOW_ID:
            values["workflow_id"] = _require_value(args, index, token)
            index += 2
        elif token == FLAG_CORRELATION_ID:
            values["correlation_id"] = _require_value(args, index, token)
            index += 2
        elif token == FLAG_ACTOR:
            values["actor"] = _require_value(args, index, token)
            index += 2
        else:
            raise CliUsageError(f"Unknown initiate flag: {token}")
    return values


def _parse_approve_args(args: Sequence[str]) -> tuple[str | None, str | None]:
    if not args:
        raise CliUsageError("approve requires a workflow_id argument")
    workflow_id = args[0]
    action: str | None = None
    index = 1
    while index < len(args):
        token = args[index]
        if token == FLAG_ACTION:
            action = _require_value(args, index, token)
            index += 2
        else:
            raise CliUsageError(f"Unknown approve flag: {token}")
    return workflow_id, action


def _require_value(args: Sequence[str], index: int, flag: str) -> str:
    if index + 1 >= len(args):
        raise CliUsageError(f"{flag} requires a value")
    return args[index + 1]
