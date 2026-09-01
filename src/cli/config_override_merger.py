"""Immutable AppConfig merge for CLI bootstrap overrides."""

from __future__ import annotations

from dataclasses import replace

from config.types import AppConfig, FailureInjectionConfig

from .errors import CliUsageError
from .types import CliConfigOverride, CliFailureInjectionOverride


class ConfigOverrideMerger:
    """Pure merge of CLI overrides into config domain objects."""

    def merge_failure_injection_override(
        self,
        base: FailureInjectionConfig,
        override: CliFailureInjectionOverride | None,
    ) -> FailureInjectionConfig:
        if override is None:
            return base
        if not override.enabled:
            return base
        from .config_override import _validate_injection_ids

        active = _validate_injection_ids(override.active_injections)
        if not active:
            raise CliUsageError("Failure injection enabled but no injection ids specified")
        return FailureInjectionConfig(enabled=True, active_injections=active)

    def merge_cli_config_override(
        self,
        base: AppConfig,
        override: CliConfigOverride | None,
    ) -> AppConfig:
        if override is None or override.failure_injection is None:
            return base
        merged_fi = self.merge_failure_injection_override(
            base.failure_injection,
            override.failure_injection,
        )
        credential_resolver = getattr(base, "_credential_resolver", None)
        if credential_resolver is not None:
            return type(base)(
                infrastructure=base.infrastructure,
                agents=base.agents,
                providers=base.providers,
                collection=base.collection,
                workflow=base.workflow,
                workers=base.workers,
                retry=base.retry,
                timeouts=base.timeouts,
                failure_injection=merged_fi,
                credential_resolver=credential_resolver,
            )
        return replace(base, failure_injection=merged_fi)


_default_merger = ConfigOverrideMerger()
