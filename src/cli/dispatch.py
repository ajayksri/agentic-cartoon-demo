"""Internal dispatch state bridging parse results to handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.types import AppConfig

from .parser import ParsedCliInvocation


@dataclass(frozen=True, slots=True)
class InitiateBootstrapState:
    """Merged local config retained for downstream spawn/export."""

    effective_config: AppConfig
    config_source_path: Path


@dataclass(frozen=True, slots=True)
class HandlerDispatchState:
    """Internal bridge from parse result to handlers."""

    parsed: ParsedCliInvocation
    initiate_bootstrap: InitiateBootstrapState | None = None
