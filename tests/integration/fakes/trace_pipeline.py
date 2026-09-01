"""Cross-process trace pipeline capture for INT-005 (IT-OBS-*).

Models API → coordinator → queue carrier → worker → fake-provider span linkage
using public ``observability.TraceContext`` and W3C ``traceparent`` carriers.
Does not import observability module internals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from observability import TraceContext
from task_queue import TRACE_CARRIER_KEY_TRACEPARENT


def _new_trace_id() -> str:
    return uuid.uuid4().hex


def _new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def traceparent_of(ctx: TraceContext) -> str:
    """Format a W3C traceparent from TraceContext."""
    return f"00-{ctx.trace_id}-{ctx.span_id}-{ctx.trace_flags:02x}"


def parse_traceparent(value: str) -> TraceContext:
    """Parse a W3C traceparent into TraceContext (remote)."""
    parts = value.strip().split("-")
    if len(parts) != 4:
        raise ValueError(f"malformed traceparent: {value!r}")
    version, trace_id, span_id, flags = parts
    if version != "00" or len(trace_id) != 32 or len(span_id) != 16:
        raise ValueError(f"malformed traceparent: {value!r}")
    return TraceContext(
        trace_id=trace_id.lower(),
        span_id=span_id.lower(),
        trace_flags=int(flags, 16),
        is_remote=True,
    )


@dataclass
class RecordedSpan:
    name: str
    service: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedLog:
    event: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedMetric:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class TracePipelineCapture:
    """In-memory export capture for composition-level IT-OBS scenarios."""

    spans: list[RecordedSpan] = field(default_factory=list)
    logs: list[CapturedLog] = field(default_factory=list)
    metrics: list[CapturedMetric] = field(default_factory=list)
    queue_carriers: list[dict[str, str]] = field(default_factory=list)

    def start_api_span(
        self,
        *,
        inbound_traceparent: str | None = None,
        workflow_id: str | None = None,
    ) -> TraceContext:
        """API ingress: extract optional client traceparent or start a root span."""
        if inbound_traceparent:
            remote = parse_traceparent(inbound_traceparent)
            span_id = _new_span_id()
            ctx = TraceContext(
                trace_id=remote.trace_id,
                span_id=span_id,
                trace_flags=remote.trace_flags,
                is_remote=False,
            )
            parent = remote.span_id
        else:
            ctx = TraceContext(
                trace_id=_new_trace_id(),
                span_id=_new_span_id(),
                trace_flags=1,
                is_remote=False,
            )
            parent = None
        attrs: dict[str, Any] = {"service.name": "api"}
        if workflow_id:
            attrs["workflow_id"] = workflow_id
        self.spans.append(
            RecordedSpan(
                name="api.initiate",
                service="api",
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                parent_span_id=parent,
                attributes=attrs,
            )
        )
        return ctx

    def coordinator_span(self, parent: TraceContext, *, workflow_id: str) -> TraceContext:
        """Coordinator consumes API trace and starts a child span."""
        child = TraceContext(
            trace_id=parent.trace_id,
            span_id=_new_span_id(),
            trace_flags=parent.trace_flags,
            is_remote=False,
        )
        self.spans.append(
            RecordedSpan(
                name="coordinator.outbox_publish",
                service="coordinator",
                trace_id=child.trace_id,
                span_id=child.span_id,
                parent_span_id=parent.span_id,
                attributes={"workflow_id": workflow_id, "service.name": "coordinator"},
            )
        )
        return child

    def inject_queue_carrier(self, ctx: TraceContext) -> dict[str, str]:
        """Write W3C carrier onto a queue message envelope (ACD-FR-035)."""
        carrier = {
            TRACE_CARRIER_KEY_TRACEPARENT: traceparent_of(ctx),
        }
        self.queue_carriers.append(dict(carrier))
        return carrier

    def worker_span_from_carrier(
        self,
        carrier: dict[str, str],
        *,
        workflow_id: str,
        task_id: str,
        attempt: int = 1,
    ) -> TraceContext:
        """Worker extracts queue carrier and starts a child span."""
        remote = parse_traceparent(carrier[TRACE_CARRIER_KEY_TRACEPARENT])
        child = TraceContext(
            trace_id=remote.trace_id,
            span_id=_new_span_id(),
            trace_flags=remote.trace_flags,
            is_remote=False,
        )
        self.spans.append(
            RecordedSpan(
                name="worker.handle_task",
                service="worker",
                trace_id=child.trace_id,
                span_id=child.span_id,
                parent_span_id=remote.span_id,
                attributes={
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                    "task_attempt": attempt,
                    "service.name": "worker",
                },
            )
        )
        return child

    def provider_span(self, parent: TraceContext, *, provider: str = "fake") -> TraceContext:
        """Fake provider span under the worker (ACD-NFR-011)."""
        child = TraceContext(
            trace_id=parent.trace_id,
            span_id=_new_span_id(),
            trace_flags=parent.trace_flags,
            is_remote=False,
        )
        self.spans.append(
            RecordedSpan(
                name="provider.generate",
                service="provider",
                trace_id=child.trace_id,
                span_id=child.span_id,
                parent_span_id=parent.span_id,
                attributes={"provider": provider, "service.name": "provider"},
            )
        )
        return child

    def run_end_to_end(
        self,
        *,
        workflow_id: str,
        task_id: str,
        inbound_traceparent: str | None = None,
        attempt: int = 1,
    ) -> TraceContext:
        """Full composition path: API → coordinator → queue → worker → provider."""
        api_ctx = self.start_api_span(
            inbound_traceparent=inbound_traceparent,
            workflow_id=workflow_id,
        )
        coord_ctx = self.coordinator_span(api_ctx, workflow_id=workflow_id)
        carrier = self.inject_queue_carrier(coord_ctx)
        worker_ctx = self.worker_span_from_carrier(
            carrier,
            workflow_id=workflow_id,
            task_id=task_id,
            attempt=attempt,
        )
        return self.provider_span(worker_ctx, provider="fake")

    def redeliver(
        self,
        carrier: dict[str, str],
        *,
        workflow_id: str,
        task_id: str,
        attempt: int,
    ) -> TraceContext:
        """Redelivery continues the same trace (IT-OBS-004)."""
        worker_ctx = self.worker_span_from_carrier(
            carrier,
            workflow_id=workflow_id,
            task_id=task_id,
            attempt=attempt,
        )
        return self.provider_span(worker_ctx, provider="fake")

    def record_idempotency_hit(
        self,
        *,
        workflow_id: str,
        task_id: str,
        trace_id: str,
    ) -> None:
        """Emit idempotency visibility in metrics + structured logs (IT-OBS-005)."""
        self.metrics.append(
            CapturedMetric(
                name="worker_idempotency_hits_total",
                value=1.0,
                labels={
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                    "outcome": "duplicate",
                },
            )
        )
        self.logs.append(
            CapturedLog(
                event="idempotency_hit",
                message="duplicate delivery skipped; prior completion reused",
                fields={
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "outcome": "duplicate",
                },
            )
        )
        # Span event on latest worker span if present
        for span in reversed(self.spans):
            if span.service == "worker" and span.trace_id == trace_id:
                span.attributes["idempotency_hit"] = True
                break

    def spans_for_trace(self, trace_id: str) -> list[RecordedSpan]:
        return [s for s in self.spans if s.trace_id == trace_id]

    def services_for_trace(self, trace_id: str) -> set[str]:
        return {s.service for s in self.spans_for_trace(trace_id)}
