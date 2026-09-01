"""Recording handler fake for contract tests."""

from __future__ import annotations

from dataclasses import dataclass

from config.types import TaskType
from worker.types import TaskHandlerOutcome, TaskHandlerResult
from workflow.types import TransitionSignal


@dataclass
class RecordingHandler:
    """Minimal handler fake with configurable outcome or error."""

    _task_type: TaskType
    calls: int = 0
    result: TaskHandlerResult | None = None
    raise_error: BaseException | None = None

    @property
    def task_type(self) -> TaskType:
        return self._task_type

    def handle(self, context: object) -> TaskHandlerResult:
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        return self.result or TaskHandlerResult(
            outcome=TaskHandlerOutcome.COMPLETED,
            transition_signal=TransitionSignal.STAGE_COMPLETED,
            result_artifact_id="art-contract-1",
        )
