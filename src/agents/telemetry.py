"""Agent telemetry — log, metric, and span seam."""

from __future__ import annotations

from typing import TYPE_CHECKING

from observability.protocols import Span
from observability.types import MetricDescriptor

if TYPE_CHECKING:
    from agents.base import AgentStage
from agents.constants import (
    LOG_CRITIC_VERDICT,
    LOG_RUN_COMPLETED,
    LOG_VALIDATION_FAILED,
    METRIC_CRITIC_VERDICT_TOTAL,
    METRIC_TOPIC_OUTCOME_TOTAL,
    METRIC_VALIDATION_TOTAL,
    SPAN_AGENT_RUN,
)
from agents.types import (
    AgentRunContext,
    CriticStatus,
    TopicSelectionOutcome,
    ValidationResult,
)


class AgentTelemetry:
    """Lazy metric registration and bounded observability emission."""

    def __init__(
        self,
        *,
        context: AgentRunContext,
        stage: AgentStage,
    ) -> None:
        self._context = context
        self._stage = stage
        self._validation_counter = None
        self._topic_outcome_counter = None
        self._critic_verdict_counter = None

    def _agent_label(self) -> str:
        return self._context.agent_id.value

    def _get_validation_counter(self) -> object:
        if self._validation_counter is None:
            self._validation_counter = self._context.meter.register_counter(
                MetricDescriptor(
                    logical_name=METRIC_VALIDATION_TOTAL,
                    metric_type="counter",
                    description="Agent output validation outcomes",
                    allowed_label_keys=frozenset({"agent", "result"}),
                ),
            )
        return self._validation_counter

    def _get_topic_outcome_counter(self) -> object:
        if self._topic_outcome_counter is None:
            self._topic_outcome_counter = self._context.meter.register_counter(
                MetricDescriptor(
                    logical_name=METRIC_TOPIC_OUTCOME_TOTAL,
                    metric_type="counter",
                    description="Topic selection stage outcomes",
                    allowed_label_keys=frozenset({"outcome"}),
                ),
            )
        return self._topic_outcome_counter

    def _get_critic_verdict_counter(self) -> object:
        if self._critic_verdict_counter is None:
            self._critic_verdict_counter = self._context.meter.register_counter(
                MetricDescriptor(
                    logical_name=METRIC_CRITIC_VERDICT_TOTAL,
                    metric_type="counter",
                    description="Critic verdict outcomes",
                    allowed_label_keys=frozenset({"status"}),
                ),
            )
        return self._critic_verdict_counter

    def start_run_span(self, *, model: str) -> Span:
        return self._context.tracer.start_span(
            SPAN_AGENT_RUN,
            attributes={
                "agent": self._agent_label(),
                "model": model,
            },
        )

    def record_validation(self, *, result: ValidationResult) -> None:
        counter = self._get_validation_counter()
        counter.add(  # type: ignore[union-attr]
            labels={"agent": self._agent_label(), "result": result.value},
        )

    def record_stage_outcome_topic(self, *, outcome: TopicSelectionOutcome) -> None:
        counter = self._get_topic_outcome_counter()
        counter.add(labels={"outcome": outcome.value})  # type: ignore[union-attr]

    def record_stage_outcome_critic(self, *, status: CriticStatus) -> None:
        counter = self._get_critic_verdict_counter()
        status_label = "pass" if status == CriticStatus.PASS else "revise"
        counter.add(labels={"status": status_label})  # type: ignore[union-attr]

    def log_run_completed(
        self,
        *,
        model: str,
        prompt_version: str,
        validation_result: ValidationResult,
    ) -> None:
        self._context.logger.info(
            LOG_RUN_COMPLETED,
            "agent run completed",
            agent=self._agent_label(),
            model=model,
            validation_result=validation_result.value,
            prompt_version=prompt_version,
        )

    def log_critic_verdict(self, *, status: CriticStatus) -> None:
        self._context.logger.info(
            LOG_CRITIC_VERDICT,
            "critic verdict",
            agent=self._agent_label(),
            status=status.value,
        )

    def log_validation_failed(self, *, validation_error_code: str) -> None:
        self._context.logger.error(
            LOG_VALIDATION_FAILED,
            "agent validation failed",
            error_class=validation_error_code,
            retryable=False,
            agent=self._agent_label(),
            validation_error_code=validation_error_code,
        )

    def finalize_span_success(self, *, span: Span) -> None:
        span.set_attribute("validation_result", ValidationResult.PASSED.value)
        span.end(status="OK")

    def finalize_span_failure(
        self,
        *,
        span: Span,
        error_class: str,
        retryable: bool,
    ) -> None:
        span.record_exception(error_class=error_class, retryable=retryable)
        span.end(status="ERROR")


class RecordingAgentTelemetry(AgentTelemetry):
    """Test subclass capturing call order for ordering proofs."""

    def __init__(self, *, context: AgentRunContext, stage: AgentStage) -> None:
        super().__init__(context=context, stage=stage)
        self.validation_calls: list[ValidationResult] = []
        self.stage_outcome_calls: list[dict[str, object]] = []
        self.log_calls: list[str] = []
        self.span_events: list[str] = []

    def record_validation(self, *, result: ValidationResult) -> None:
        self.validation_calls.append(result)
        super().record_validation(result=result)

    def record_stage_outcome_topic(self, *, outcome: TopicSelectionOutcome) -> None:
        self.stage_outcome_calls.append({"type": "topic", "outcome": outcome})
        super().record_stage_outcome_topic(outcome=outcome)

    def record_stage_outcome_critic(self, *, status: CriticStatus) -> None:
        self.stage_outcome_calls.append({"type": "critic", "status": status})
        super().record_stage_outcome_critic(status=status)

    def log_validation_failed(self, *, validation_error_code: str) -> None:
        self.log_calls.append(LOG_VALIDATION_FAILED)
        super().log_validation_failed(validation_error_code=validation_error_code)

    def finalize_span_failure(
        self,
        *,
        span: Span,
        error_class: str,
        retryable: bool,
    ) -> None:
        self.span_events.append(f"failure:{error_class}")
        super().finalize_span_failure(span=span, error_class=error_class, retryable=retryable)

    def finalize_span_success(self, *, span: Span) -> None:
        self.span_events.append("success")
        super().finalize_span_success(span=span)
