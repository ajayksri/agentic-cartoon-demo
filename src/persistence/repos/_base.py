"""Shared repository helpers for connection scoping and transaction guards."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import psycopg
from psycopg.types.json import Json

from persistence.errors import PersistenceConnectionError, PersistenceTransactionError
from persistence.errors_internal import ErrorTranslator
from persistence.events import (
    MetricsRecorder,
    NoOpMetricsRecorder,
    NoOpOperationLogger,
    OperationLogger,
    PersistenceOperationEvent,
)
from persistence.session import get_active_session

if TYPE_CHECKING:
    from persistence.errors import PersistenceError
    from persistence.pool import ConnectionPoolManager
    from persistence.repos._mappers import RowMapper
    from persistence.types import JsonValue


def _jsonb(value: JsonValue) -> Json:
    """Adapt JSON/JSONB parameters for psycopg v3."""
    return Json(value)


class PostgresRepoBase:
  """Base class for PostgreSQL repository implementations."""

  def __init__(
      self,
      pool_manager: ConnectionPoolManager | None = None,
      *,
      mapper: RowMapper | None = None,
      error_translator: ErrorTranslator | None = None,
      operation_logger: OperationLogger | None = None,
      metrics_recorder: MetricsRecorder | None = None,
  ) -> None:
      from persistence.repos._mappers import RowMapper as _RowMapper

      self._pool_manager = pool_manager
      self._mapper = mapper or _RowMapper()
      self._error_translator = error_translator or ErrorTranslator()
      self._operation_logger = operation_logger or NoOpOperationLogger()
      self._metrics_recorder = metrics_recorder or NoOpMetricsRecorder()

  def _require_active_transaction(self, operation: str) -> None:
      session = get_active_session()
      if session is None or not session.in_transaction:
          raise PersistenceTransactionError(
              f"Operation {operation} requires an active transaction"
          )

  def _connection(self) -> psycopg.Connection:
      session = get_active_session()
      if session is not None and session.in_transaction:
          return session.connection
      raise PersistenceTransactionError("No active transactional connection")

  @contextmanager
  def _borrow_connection(self) -> Iterator[psycopg.Connection]:
      session = get_active_session()
      if session is not None and session.in_transaction:
          yield session.connection
      elif self._pool_manager is not None:
          with self._pool_manager.acquire() as connection:
              yield connection
      else:
          raise PersistenceConnectionError(
              "Persistence connection error during acquire"
          )

  def _record_success(self, operation: str) -> None:
      self._metrics_recorder.increment(operation, "success")

  def _raise_mapped(
      self,
      exc: BaseException,
      *,
      operation: str,
      entity_id: str | None = None,
  ) -> None:
      translated = self._error_translator.translate(
          exc,
          operation=operation,
          entity_id=entity_id,
      )
      self._log_error(operation, translated, entity_id)
      raise translated from exc

  def _log_error(
      self,
      operation: str,
      exc: PersistenceError,
      entity_id: str | None,
  ) -> None:
      self._operation_logger.log_operation(
          PersistenceOperationEvent(
              operation=operation,
              error_code=exc.code,
              entity_id=entity_id,
          )
      )
      self._metrics_recorder.increment(operation, "error")
