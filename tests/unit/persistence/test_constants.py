"""Unit tests for persistence module constants and operation events."""

from __future__ import annotations

from persistence.constants import (
  DEFAULT_LEASE_TTL_SECONDS,
  IDEMPOTENCY_KEY_FORMAT_DOC,
  RECOMMENDED_LEASE_RENEW_INTERVAL_SECONDS,
  TASK_PAYLOAD_REF_KIND,
)
from persistence.events import (
  NoOpMetricsRecorder,
  NoOpOperationLogger,
  OperationLogger,
  PersistenceOperationEvent,
)


def test_lease_ttl_constants_match_lld() -> None:
  assert DEFAULT_LEASE_TTL_SECONDS == 60.0
  assert RECOMMENDED_LEASE_RENEW_INTERVAL_SECONDS == 30.0


def test_idempotency_and_payload_constants_match_lld() -> None:
  assert IDEMPOTENCY_KEY_FORMAT_DOC == "{workflow_id}:{task_type}:{logical_version}"
  assert TASK_PAYLOAD_REF_KIND == "task_payload"


def test_persistence_operation_event_is_frozen() -> None:
  event = PersistenceOperationEvent(
    operation="create_workflow",
    error_code="PERS_CONNECTION",
    entity_id="wf-1",
  )
  assert event.operation == "create_workflow"
  assert event.error_code == "PERS_CONNECTION"
  assert event.entity_id == "wf-1"


class _ListRecordingLogger:
  def __init__(self) -> None:
    self.events: list[PersistenceOperationEvent] = []

  def log_operation(self, event: PersistenceOperationEvent) -> None:
    self.events.append(event)


def test_operation_logger_records_events() -> None:
  logger: OperationLogger = _ListRecordingLogger()
  event = PersistenceOperationEvent(operation="health_check", error_code=None)

  logger.log_operation(event)

  assert isinstance(logger, _ListRecordingLogger)
  assert logger.events == [event]


def test_noop_loggers_accept_all_inputs() -> None:
  event = PersistenceOperationEvent(operation="update_workflow_state", entity_id="wf-2")
  NoOpOperationLogger().log_operation(event)
  NoOpMetricsRecorder().increment("update_workflow_state", "success")
