"""Contract-test doubles for the API module (not exported from package root)."""

from __future__ import annotations

from api.fakes.observability import FakeCorrelationContext, RecordingLogger, RecordingTracer
from api.fakes.probes import FakeReadinessProbe
from api.fakes.workflow import FakeWorkflowEngine

__all__ = [
    "FakeCorrelationContext",
    "FakeReadinessProbe",
    "FakeWorkflowEngine",
    "RecordingLogger",
    "RecordingTracer",
]
