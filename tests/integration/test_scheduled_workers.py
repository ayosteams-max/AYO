from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert

from BACKEND.dispatch.scheduler import WorkerHealth
from BACKEND.persistence.tables import reservation_checkpoints
from BACKEND.scheduled.workers import (
    PostgresCheckpointClaims,
    PostgresScheduledWorkerLock,
    ScheduledWorkerCoordinator,
    ScheduledWorkerKind,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


class Processor:
    def __init__(self) -> None:
        self.processed: list[UUID] = []

    def process(self, checkpoint, *, now):
        del now
        self.processed.append(checkpoint.checkpoint_id)


def test_transactional_checkpoint_claim_is_restart_safe_and_duplicate_free(
    postgres_engine, postgres_composition
) -> None:
    from tests.integration.test_scheduled_dispatch_integration import (
        app,
        command,
        subject,
    )

    booker, passenger = subject(), subject()
    integration, _ = app(postgres_composition, passenger)
    created, _ = integration.create(
        booker, command(), idempotency_key="worker-checkpoint-create", now=NOW
    )
    checkpoint_id = uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(reservation_checkpoints).values(
                checkpoint_id=checkpoint_id,
                reservation_id=created.reservation_id,
                payload={
                    "kind": "recovery",
                    "due_at": NOW.isoformat(),
                    "completed_at": None,
                    "attempt_count": 0,
                },
                created_at=NOW,
            )
        )
    processor = Processor()
    coordinator = ScheduledWorkerCoordinator(
        ScheduledWorkerKind.RECOVERY,
        PostgresScheduledWorkerLock(postgres_engine, ScheduledWorkerKind.RECOVERY),
        PostgresCheckpointClaims(postgres_engine),
        processor,
        worker_id="scheduled-recovery-test",
        health=WorkerHealth(),
        batch_limit=10,
    )
    first = coordinator.run_once(now=NOW)
    second = coordinator.run_once(now=NOW)
    assert first.completed == 1
    assert second.claimed == 0
    assert processor.processed == [checkpoint_id]


def test_postgres_advisory_lock_prevents_overlapping_worker_runs(postgres_engine):
    barrier = Barrier(2)
    lock = PostgresScheduledWorkerLock(postgres_engine, ScheduledWorkerKind.PLANNING)

    def acquire():
        barrier.wait()
        with lock.acquire() as acquired:
            barrier.wait()
            return acquired

    # The winner waits while the loser observes the held transaction lock.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(acquire) for _ in range(2)]
        outcomes = [future.result(timeout=5) for future in futures]
    assert sum(outcomes) == 1
