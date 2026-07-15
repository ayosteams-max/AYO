from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest

from BACKEND.dispatch.scheduler import (
    DispatchRecoveryCoordinator,
    PostgresRecoveryWorkerLock,
    WorkerHealth,
)
from BACKEND.dispatch.worker import RecoveryResult

pytestmark = pytest.mark.integration


class BlockingWorker:
    def __init__(self, entered: Event, release: Event) -> None:
        self.entered = entered
        self.release = release

    def run_once(self, *, now=None):
        del now
        self.entered.set()
        assert self.release.wait(timeout=5)
        return RecoveryResult(0, 0, 0)


class CountingWorker:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self, *, now=None):
        del now
        self.calls += 1
        return RecoveryResult(0, 0, 0)


def test_postgres_advisory_lock_prevents_overlapping_recovery(postgres_engine) -> None:
    entered = Event()
    release = Event()
    first = DispatchRecoveryCoordinator(
        BlockingWorker(entered, release),
        PostgresRecoveryWorkerLock(postgres_engine),
        WorkerHealth(),
    )
    second_worker = CountingWorker()
    second = DispatchRecoveryCoordinator(
        second_worker,
        PostgresRecoveryWorkerLock(postgres_engine),
        WorkerHealth(),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        running = executor.submit(first.run_once, now=datetime.now(UTC))
        assert entered.wait(timeout=5)
        skipped = executor.submit(second.run_once, now=datetime.now(UTC)).result()
        release.set()
        completed = running.result()
    assert completed.ran
    assert not skipped.ran
    assert second_worker.calls == 0
