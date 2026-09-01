"""Runtime contract-test fakes — not exported from runtime public surface."""

from .bootstrap import FakeCompositionRoot, RecordingCallOrder
from .persistence import FakePersistenceBundle, FakePoolManager, build_fake_persistence_bundle
from .task_queue import FakeConnectionManager, FakeTaskQueue
from .worker_loop import FakeWorkerLoop
from .workflow_engine import FakeWorkflowEngine

__all__ = [
    "FakeCompositionRoot",
    "FakeConnectionManager",
    "FakePersistenceBundle",
    "FakePoolManager",
    "FakeTaskQueue",
    "FakeWorkerLoop",
    "FakeWorkflowEngine",
    "RecordingCallOrder",
    "build_fake_persistence_bundle",
]
