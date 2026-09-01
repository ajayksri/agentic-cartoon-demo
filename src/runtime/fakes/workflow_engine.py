"""Workflow engine spy for runtime contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.types import AppConfig
from workflow.types import ReconciliationResult


@dataclass
class FakeWorkflowEngine:
    """Records reconcile_stuck_workflows invocations (RT-TC-009)."""

    reconcile_calls: list[dict[str, Any]] = field(default_factory=list)

    def reconcile_stuck_workflows(
        self,
        *,
        config: AppConfig,
        batch_size: int = 100,
    ) -> ReconciliationResult:
        self.reconcile_calls.append({"config": config, "batch_size": batch_size})
        return ReconciliationResult(scanned_count=0, repaired_count=0, reports=())
