"""Controllable persistence bundle for runtime contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from persistence.bootstrap import PersistenceBundle
from persistence.fakes.artifact import InMemoryArtifactRepo
from persistence.fakes.idempotency import InMemoryIdempotencyRepo
from persistence.fakes.outbox import InMemoryOutboxRepo
from persistence.fakes.task_lease import InMemoryTaskLeaseRepo
from persistence.fakes.transaction import InMemoryTransactionManager
from persistence.fakes.workflow import InMemoryWorkflowRepo


@dataclass
class FakePoolManager:
    """Pool manager stub with controllable health_check behavior."""

    health_ok: bool = True
    health_delay_seconds: float = 0.0
    health_check_calls: int = 0

    def health_check(self) -> None:
        import time

        self.health_check_calls += 1
        if self.health_delay_seconds > 0:
            time.sleep(self.health_delay_seconds)
        if not self.health_ok:
            raise RuntimeError("postgres unavailable")

    def close(self) -> None:
        return None


def build_fake_persistence_bundle(
    *,
    pool_manager: FakePoolManager | None = None,
) -> PersistenceBundle:
    """Assemble a persistence bundle using in-memory repos."""
    manager = pool_manager or FakePoolManager()
    txn = InMemoryTransactionManager()
    return PersistenceBundle(
        transaction_manager=txn,
        workflow_repo=InMemoryWorkflowRepo(transaction_manager=txn),
        artifact_repo=InMemoryArtifactRepo(transaction_manager=txn),
        idempotency_repo=InMemoryIdempotencyRepo(transaction_manager=txn),
        outbox_repo=InMemoryOutboxRepo(transaction_manager=txn),
        task_lease_repo=InMemoryTaskLeaseRepo(transaction_manager=txn),
        pool_manager=manager,  # type: ignore[arg-type]
    )


@dataclass
class FakePersistenceBundle:
    """Runtime test double wrapping PersistenceBundle with pool spy."""

    bundle: PersistenceBundle
    pool_manager: FakePoolManager = field(default_factory=FakePoolManager)

    @classmethod
    def create(
        cls,
        *,
        health_ok: bool = True,
        health_delay_seconds: float = 0.0,
    ) -> FakePersistenceBundle:
        pool = FakePoolManager(
            health_ok=health_ok,
            health_delay_seconds=health_delay_seconds,
        )
        return cls(bundle=build_fake_persistence_bundle(pool_manager=pool), pool_manager=pool)
