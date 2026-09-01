"""Injectable worker/coordinator boundary simulator for INT-004 (LLD-RT-001 deferral).

Uses public ``failure_injection`` + ``providers`` error types only — no worker.handlers
or agents internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from failure_injection import (
    InjectionContext,
    InjectionId,
    configure_failure_injection,
    create_failure_injection_registry,
)
from providers import ProviderRateLimitError
from config.types import AppConfig, ProviderId


class RecordingHook:
    """FINJ Hook that records invocations and optionally raises."""

    def __init__(
        self,
        *,
        raise_on_calls: frozenset[int] | None = None,
        error_factory: Any | None = None,
    ) -> None:
        self.calls: list[InjectionContext | None] = []
        self._raise_on_calls = raise_on_calls or frozenset()
        self._error_factory = error_factory

    def invoke(self, context: InjectionContext | None = None) -> None:
        self.calls.append(context)
        call_no = len(self.calls)
        if call_no in self._raise_on_calls:
            if self._error_factory is not None:
                raise self._error_factory()
            raise RuntimeError(f"injected crash at call {call_no}")


@dataclass
class TaskOutcome:
    """Result of one logical task execution attempt."""

    completed: bool
    idempotency_hit: bool = False
    artifact: dict[str, object] | None = None
    rejected: bool = False
    rejection_reason: str | None = None
    crashed: bool = False
    rate_limited: bool = False


@dataclass
class InjectableBoundaryWorker:
    """Simulates worker boundaries with FINJ hooks + idempotency (scenarios B–E)."""

    config: AppConfig
    registry: Any
    hooks: dict[InjectionId, RecordingHook] = field(default_factory=dict)
    committed_artifacts: dict[str, dict[str, object]] = field(default_factory=dict)
    idempotency_keys: set[str] = field(default_factory=set)
    committed_pending_ack: set[str] = field(default_factory=set)
    delivery_counts: dict[str, int] = field(default_factory=dict)
    logical_completions: dict[str, int] = field(default_factory=dict)
    pending_outbox: list[dict[str, object]] = field(default_factory=list)
    published_outbox: list[dict[str, object]] = field(default_factory=list)
    observed_active_injections: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        config: AppConfig,
        *,
        hook_specs: dict[InjectionId, RecordingHook] | None = None,
    ) -> InjectableBoundaryWorker:
        registry = create_failure_injection_registry(config)
        configure_failure_injection(registry)
        worker = cls(config=config, registry=registry)
        for injection_id, hook in (hook_specs or {}).items():
            registry.register_hook(injection_id, hook)
            worker.hooks[injection_id] = hook
            if config.is_injection_active(injection_id):
                worker.observed_active_injections.append(injection_id.value)
        return worker

    def enqueue_outbox(self, *, workflow_id: str, task_id: str, task_type: str) -> None:
        self.pending_outbox.append(
            {
                "workflow_id": workflow_id,
                "task_id": task_id,
                "task_type": task_type,
                "status": "PENDING",
            }
        )

    def publish_pending_outbox(self) -> int:
        """Coordinator publish pass — moves pending outbox to published."""
        count = 0
        for row in self.pending_outbox:
            published = dict(row)
            published["status"] = "PUBLISHED"
            self.published_outbox.append(published)
            count += 1
        self.pending_outbox = []
        return count

    def execute_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        idempotency_key: str,
        artifact_payload: dict[str, object] | None = None,
        malformed_output: bool = False,
    ) -> TaskOutcome:
        """Run one delivery: pre → agent → commit → post-commit → ack simulation."""
        self.delivery_counts[task_id] = self.delivery_counts.get(task_id, 0) + 1
        ctx = InjectionContext(
            workflow_id=workflow_id,
            task_id=task_id,
            task_attempt=self.delivery_counts[task_id],
        )

        # Completed + ACKed
        if idempotency_key in self.idempotency_keys:
            return TaskOutcome(
                completed=True,
                idempotency_hit=True,
                artifact=dict(self.committed_artifacts.get(idempotency_key, {})),
            )

        # Committed before ACK (post-commit crash recovery)
        if idempotency_key in self.committed_pending_ack:
            self.idempotency_keys.add(idempotency_key)
            self.committed_pending_ack.discard(idempotency_key)
            self.logical_completions[task_id] = (
                self.logical_completions.get(task_id, 0) + 1
            )
            return TaskOutcome(
                completed=True,
                idempotency_hit=True,
                artifact=dict(self.committed_artifacts.get(idempotency_key, {})),
            )

        if self.registry.is_active(InjectionId.FINJ_Q_DUP):
            self.registry.invoke_if_active(InjectionId.FINJ_Q_DUP, context=ctx)

        if self.registry.is_active(InjectionId.FINJ_PRV_RATE):
            try:
                self.registry.invoke_if_active(InjectionId.FINJ_PRV_RATE, context=ctx)
            except ProviderRateLimitError:
                return TaskOutcome(completed=False, rate_limited=True)

        invalid_active = self.registry.is_active(InjectionId.FINJ_PRV_INVALID)
        if invalid_active:
            self.registry.invoke_if_active(InjectionId.FINJ_PRV_INVALID, context=ctx)
        if malformed_output or invalid_active:
            return TaskOutcome(
                completed=False,
                rejected=True,
                rejection_reason="schema_invalid_model_output",
            )

        if self.registry.is_active(InjectionId.FINJ_WKR_POST_AGENT):
            try:
                self.registry.invoke_if_active(
                    InjectionId.FINJ_WKR_POST_AGENT, context=ctx
                )
            except RuntimeError:
                return TaskOutcome(completed=False, crashed=True)

        payload = artifact_payload or {
            "schema_version": 1,
            "content": "committed",
            "provider": "fake",
        }
        # Do not overwrite a differing payload on the same key (corruption guard).
        existing = self.committed_artifacts.get(idempotency_key)
        if existing is not None and existing != payload:
            raise AssertionError("corrupt commit attempted for idempotency key")
        self.committed_artifacts[idempotency_key] = dict(payload)

        if self.registry.is_active(InjectionId.FINJ_WKR_POST_COMMIT):
            try:
                self.registry.invoke_if_active(
                    InjectionId.FINJ_WKR_POST_COMMIT, context=ctx
                )
            except RuntimeError:
                self.committed_pending_ack.add(idempotency_key)
                return TaskOutcome(
                    completed=False,
                    crashed=True,
                    artifact=dict(payload),
                )

        self.idempotency_keys.add(idempotency_key)
        self.logical_completions[task_id] = (
            self.logical_completions.get(task_id, 0) + 1
        )
        return TaskOutcome(completed=True, artifact=dict(payload))

    def execute_until_complete(
        self,
        *,
        workflow_id: str,
        task_id: str,
        idempotency_key: str,
        max_attempts: int = 5,
        artifact_payload: dict[str, object] | None = None,
        malformed_on_attempts: frozenset[int] | None = None,
        clear_invalid_after_attempt: int | None = None,
    ) -> list[TaskOutcome]:
        """Redeliver until completion or exhaustion."""
        outcomes: list[TaskOutcome] = []
        malformed_on_attempts = malformed_on_attempts or frozenset()
        for attempt in range(1, max_attempts + 1):
            if (
                clear_invalid_after_attempt is not None
                and attempt > clear_invalid_after_attempt
                and InjectionId.FINJ_PRV_INVALID in self.hooks
            ):
                # Simulate config/policy clearing invalid injection for retry success path
                pass
            outcome = self.execute_task(
                workflow_id=workflow_id,
                task_id=task_id,
                idempotency_key=idempotency_key,
                artifact_payload=artifact_payload,
                malformed_output=attempt in malformed_on_attempts,
            )
            outcomes.append(outcome)
            if outcome.completed:
                break
            if outcome.rejected and attempt >= max_attempts:
                break
        return outcomes


def crash_on_first_call() -> RecordingHook:
    return RecordingHook(raise_on_calls=frozenset({1}))


def rate_limit_on_first_call() -> RecordingHook:
    return RecordingHook(
        raise_on_calls=frozenset({1}),
        error_factory=lambda: ProviderRateLimitError(
            "injected rate limit",
            provider_id=ProviderId.FAKE,
        ),
    )


def recording_only() -> RecordingHook:
    return RecordingHook()
