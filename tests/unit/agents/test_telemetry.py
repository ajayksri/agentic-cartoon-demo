"""Pre-code test mold for AGT-008 — AgentTelemetry (LLD §4.8, §11)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest

from agents import ValidationResult
from config.types import AgentId


_PROMPT_TEXT = "TOP_SECRET_PROMPT_DO_NOT_LOG"
_RESPONSE_TEXT = "TOP_SECRET_RESPONSE_DO_NOT_LOG"


@contextmanager
def _observability_fakes() -> Iterator[tuple[object, object, object]]:
    from observability import get_correlation_context
    from observability.bootstrap import _bootstrap_for_tests, _reset_observability_state
    from observability.fakes import CapturingMeter, InMemoryLogger, RecordingTracer
    from types import SimpleNamespace

    config = SimpleNamespace(
        service_name="agents-test",
        log_level="DEBUG",
        strict_telemetry_errors=True,
    )
    _reset_observability_state()
    _bootstrap_for_tests(config=config)
    with get_correlation_context().bind(
        workflow_id="wf-test",
        task_id="task-test",
        task_attempt=1,
    ):
        yield InMemoryLogger, CapturingMeter, RecordingTracer
    _reset_observability_state()


def _run_context(*, logger: object, meter: object, tracer: object) -> object:
    from agents import AgentRunContext
    from config.app_config import AppConfigFactory
    from config.credentials import CredentialResolver
    from config.draft import (
        AgentDraft,
        BackoffDraft,
        CollectionDraft,
        ConfigDraft,
        FailureInjectionDraft,
        InfrastructureDraft,
        PostgresDraft,
        ProviderDraft,
        RedisDraft,
        RetryPolicyDraft,
        TimeoutDraft,
        WorkerDraft,
        WorkflowDraft,
    )
    from config.types import ProviderId, TaskType
    from providers import create_provider

    backoff = BackoffDraft(initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
    retry_policy = RetryPolicyDraft(max_attempts=3, backoff=backoff)
    draft = ConfigDraft(
        config_version="1",
        infrastructure=InfrastructureDraft(
            postgres=PostgresDraft(
                host="localhost",
                port=5432,
                database="cartoon",
                user_env="POSTGRES_USER",
                password_env="POSTGRES_PASSWORD",
            ),
            redis=RedisDraft(host="localhost", port=6379, db=0, password_env=None),
        ),
        agents={
            AgentId.TOPIC_SELECTOR: AgentDraft(
                provider=ProviderId.FAKE,
                model="fake-model",
                prompt_file="tests/fixtures/agents/prompts/topic_selector.txt",
            ),
        },
        providers={
            ProviderId.FAKE: ProviderDraft(
                api_key_env="FAKE_API_KEY",
                rate_limit_per_minute=None,
                pricing=None,
            ),
        },
        collection=CollectionDraft(candidate_count=10, scoring=None),
        workflow=WorkflowDraft(max_scenario_revisions=2),
        workers=WorkerDraft(
            topic_selector_concurrency=1,
            scenario_generator_concurrency=1,
            critic_concurrency=1,
        ),
        retry={task: retry_policy for task in TaskType},
        timeouts={
            ProviderId.FAKE: TimeoutDraft(
                connect_seconds=None,
                read_seconds=60.0,
                total_seconds=None,
            ),
        },
        failure_injection=FailureInjectionDraft(enabled=False, active_injections=[]),
    )
    config = AppConfigFactory(credential_resolver=CredentialResolver()).build(draft)
    provider = create_provider(provider_id=ProviderId.FAKE, config=config)
    return AgentRunContext(
        agent_id=AgentId.TOPIC_SELECTOR,
        workflow_id="wf-test",
        task_id="task-test",
        task_attempt=1,
        config=config,
        provider=provider,
        logger=logger,
        meter=meter,
        tracer=tracer,
    )


def test_lazy_counter_registration_not_at_import() -> None:
    """CG-AGT-HLD-003: instruments registered on first use, not import."""
    import agents.telemetry as telemetry_module

    assert not getattr(telemetry_module, "_INSTRUMENTS_REGISTERED", False)


def test_record_validation_registers_counter_with_allowed_labels() -> None:
    from agents.base import AgentStage
    from agents.telemetry import AgentTelemetry
    from observability import get_logger, get_meter, get_tracer

    with _observability_fakes():
        context = _run_context(
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        telemetry = AgentTelemetry(context=context, stage=AgentStage.TOPIC_SELECTION)
        telemetry.record_validation(result=ValidationResult.PASSED)

        meter = get_meter()
        assert any(
            emission[0] == "agent_validation_total"
            for emission in meter.emissions  # type: ignore[attr-defined]
        )


def test_recording_agent_telemetry_captures_call_order() -> None:
    """AGT-TC-041 seam: validation recorded before raise."""
    from agents.base import AgentStage
    from agents.telemetry import RecordingAgentTelemetry
    from observability import get_logger, get_meter, get_tracer

    with _observability_fakes():
        context = _run_context(
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        telemetry = RecordingAgentTelemetry(context=context, stage=AgentStage.CRITIC)
        span = telemetry.start_run_span(model="fake-model")
        telemetry.record_validation(result=ValidationResult.FAILED)
        telemetry.log_validation_failed(validation_error_code="AGT_OUTPUT")
        telemetry.finalize_span_failure(span=span, error_class="AGT_OUTPUT", retryable=False)

    assert telemetry.validation_calls == [ValidationResult.FAILED]
    assert telemetry.log_calls
    assert telemetry.span_events


def test_logs_omit_prompt_and_response_text() -> None:
    """AGT-TC-061 unit-level: no prompt/response in log records."""
    from agents.base import AgentStage
    from agents.telemetry import AgentTelemetry
    from observability import get_logger, get_meter, get_tracer
    from observability.fakes import InMemoryLogger

    with _observability_fakes():
        context = _run_context(
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        telemetry = AgentTelemetry(context=context, stage=AgentStage.TOPIC_SELECTION)
        telemetry.log_run_completed(
            model="fake-model",
            prompt_version="abc123",
            validation_result=ValidationResult.PASSED,
        )

        logger = get_logger()
        assert isinstance(logger, InMemoryLogger)
        joined = "\n".join(logger.records)
        assert _PROMPT_TEXT not in joined
        assert _RESPONSE_TEXT not in joined


def test_provider_failure_uses_provider_error_class_on_span() -> None:
    from agents.base import AgentStage
    from agents.telemetry import AgentTelemetry
    from observability import get_logger, get_meter, get_tracer
    from config.types import ProviderId
    from providers import ProviderErrorClass, ProviderTimeoutError

    with _observability_fakes():
        context = _run_context(
            logger=get_logger(),
            meter=get_meter(),
            tracer=get_tracer(),
        )
        telemetry = AgentTelemetry(context=context, stage=AgentStage.CRITIC)
        span = telemetry.start_run_span(model="fake-model")
        error = ProviderTimeoutError("timeout", provider_id=ProviderId.FAKE)
        telemetry.record_validation(result=ValidationResult.FAILED)
        telemetry.log_validation_failed(validation_error_code=error.code)
        telemetry.finalize_span_failure(
            span=span,
            error_class=error.error_class.value,
            retryable=error.retryable,
        )

    assert error.error_class == ProviderErrorClass.TIMEOUT
