"""Workflow observability wiring (LLD §13)."""

from __future__ import annotations

from dataclasses import dataclass, field

from observability import get_logger, get_meter, get_tracer
from observability.protocols import Counter, Logger, Meter, Span, Tracer
from observability.types import MetricDescriptor


@dataclass
class CapturedLogEvent:
    event: str
    level: str
    fields: dict[str, object]


@dataclass
class CapturedMetric:
    name: str
    labels: dict[str, str]
    value: float = 1.0


class WorkflowTelemetry:
    """Emits workflow lifecycle logs, spans, and metrics."""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self._logger = logger or get_logger()
        self._tracer = tracer or get_tracer()
        meter_impl = meter or get_meter()
        self._transition_counter = meter_impl.register_counter(
            MetricDescriptor(
                logical_name="workflow_transitions_total",
                metric_type="counter",
                description="Workflow transitions",
                allowed_label_keys=frozenset({"signal", "task_type"}),
            )
        )
        self._repair_counter = meter_impl.register_counter(
            MetricDescriptor(
                logical_name="workflow_reconciliation_repairs_total",
                metric_type="counter",
                description="Workflow reconciliation repairs",
                allowed_label_keys=frozenset({"repair_action"}),
            )
        )
        self._error_counter = meter_impl.register_counter(
            MetricDescriptor(
                logical_name="workflow_transition_errors_total",
                metric_type="counter",
                description="Workflow transition errors",
                allowed_label_keys=frozenset({"error_class"}),
            )
        )

    def emit_initiated(self, *, workflow_id: str) -> Span:
        span = self._tracer.start_span("workflow.initiate_workflow")
        span.set_attribute("workflow_id", workflow_id)
        self._logger.info(
            "workflow_initiated",
            "workflow initiated",
            workflow_id=workflow_id,
            to_state="COLLECTING",
        )
        return span

    def emit_transition(
        self,
        *,
        workflow_id: str,
        from_state: str,
        to_state: str,
        signal: str,
        task_type: str | None,
    ) -> None:
        self._logger.info(
            "workflow_transition",
            "workflow transition applied",
            workflow_id=workflow_id,
            from_state=from_state,
            to_state=to_state,
            signal=signal,
        )

    def emit_approval(
        self,
        *,
        workflow_id: str,
        action: str,
        from_state: str,
        to_state: str,
    ) -> None:
        self._logger.info(
            "approval_applied",
            "approval action applied",
            workflow_id=workflow_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
        )

    def emit_reconciliation_repair(
        self, *, workflow_id: str, repair_action: str, repaired: bool
    ) -> None:
        self._logger.info(
            "reconciliation_repair",
            "reconciliation repair attempted",
            workflow_id=workflow_id,
            repair_action=repair_action,
            repaired=repaired,
        )

    def emit_invalid_transition(
        self,
        *,
        workflow_id: str,
        error_class: str,
        from_state: str,
        signal: str,
    ) -> None:
        self._logger.warning(
            "workflow_invalid_transition",
            "invalid workflow transition",
            workflow_id=workflow_id,
            error_class=error_class,
            from_state=from_state,
            signal=signal,
        )

    def record_transition_metric(self, *, signal: str, task_type: str | None) -> None:
        self._transition_counter.add(
            1.0, labels={"signal": signal, "task_type": task_type or "none"}
        )

    def record_repair_metric(self, *, repair_action: str) -> None:
        self._repair_counter.add(1.0, labels={"repair_action": repair_action})

    def record_transition_error_metric(self, *, error_class: str) -> None:
        self._error_counter.add(1.0, labels={"error_class": error_class})


class RecordingWorkflowTelemetry(WorkflowTelemetry):
    """Captures log events, span names, and metric recordings for assertions."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.log_events: list[CapturedLogEvent] = []
        self.span_names: list[str] = []
        self.metrics: list[CapturedMetric] = []

    def emit_initiated(self, *, workflow_id: str) -> Span:
        self.span_names.append("workflow.initiate_workflow")
        return super().emit_initiated(workflow_id=workflow_id)

    def emit_transition(self, **kwargs: object) -> None:
        self.log_events.append(
            CapturedLogEvent(event="workflow_transition", level="INFO", fields=dict(kwargs))
        )
        super().emit_transition(**kwargs)  # type: ignore[arg-type]

    def emit_approval(self, **kwargs: object) -> None:
        self.log_events.append(
            CapturedLogEvent(event="approval_applied", level="INFO", fields=dict(kwargs))
        )
        super().emit_approval(**kwargs)  # type: ignore[arg-type]

    def emit_reconciliation_repair(self, **kwargs: object) -> None:
        self.log_events.append(
            CapturedLogEvent(
                event="reconciliation_repair", level="INFO", fields=dict(kwargs)
            )
        )
        super().emit_reconciliation_repair(**kwargs)  # type: ignore[arg-type]

    def emit_invalid_transition(self, **kwargs: object) -> None:
        self.log_events.append(
            CapturedLogEvent(
                event="workflow_invalid_transition", level="WARNING", fields=dict(kwargs)
            )
        )
        super().emit_invalid_transition(**kwargs)  # type: ignore[arg-type]

    def record_transition_metric(self, *, signal: str, task_type: str | None) -> None:
        self.metrics.append(
            CapturedMetric(
                name="workflow_transitions_total",
                labels={"signal": signal, "task_type": task_type or "none"},
            )
        )
        super().record_transition_metric(signal=signal, task_type=task_type)

    def record_repair_metric(self, *, repair_action: str) -> None:
        self.metrics.append(
            CapturedMetric(
                name="workflow_reconciliation_repairs_total",
                labels={"repair_action": repair_action},
            )
        )
        super().record_repair_metric(repair_action=repair_action)

    def record_transition_error_metric(self, *, error_class: str) -> None:
        self.metrics.append(
            CapturedMetric(
                name="workflow_transition_errors_total",
                labels={"error_class": error_class},
            )
        )
        super().record_transition_error_metric(error_class=error_class)

    def clear(self) -> None:
        self.log_events.clear()
        self.span_names.clear()
        self.metrics.clear()
