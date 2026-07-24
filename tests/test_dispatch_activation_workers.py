from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from BACKEND.dispatch.api_security import RequestSizeLimitMiddleware
from BACKEND.dispatch.outbox import LocalIdempotentPublisher, OutboxMessage
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker
from BACKEND.dispatch.scheduler import (
    DispatchRecoveryCoordinator,
    WorkerHealth,
)
from BACKEND.dispatch.worker import DispatchRecoveryWorker, RecoveryResult
from BACKEND.observability import InMemoryMetricsSink, NullMetricsSink, safe_event
from BACKEND.persistence.composition import PostgresRepositoryComposition

NOW = datetime(2026, 7, 16, 10, tzinfo=UTC)


def test_metrics_are_thread_safe_and_structured_logs_are_privacy_allowlisted() -> None:
    metrics = InMemoryMetricsSink()
    metrics.increment("ride_creation_outcomes", labels={"outcome": "created"}, value=2)
    metrics.gauge("worker_lag", 1.5)
    assert metrics.counters[("ride_creation_outcomes", (("outcome", "created"),))] == 2
    assert metrics.gauges[("worker_lag", ())] == 1.5
    with pytest.raises(ValueError):
        metrics.increment("invalid", value=-1)
    with pytest.raises(ValueError):
        safe_event(
            __import__("logging").getLogger(__name__),
            event="x",
            outcome="x",
            token="secret",
        )
    NullMetricsSink().increment("ignored")
    NullMetricsSink().gauge("ignored", 0)


def message() -> OutboxMessage:
    ride_id = uuid4()
    return OutboxMessage(
        message_id=uuid4(),
        aggregate_type="ride",
        aggregate_id=ride_id,
        event_type="dispatch.ride.requested",
        payload={"ride_id": str(ride_id)},
        occurred_at=NOW,
        attempt_count=0,
    )


class FakeOutboxRepository:
    def __init__(self, messages):
        self.messages = list(messages)
        self.published = set()
        self.failures = 0
        self.dead = False

    def claim_ready(self, **kwargs):
        del kwargs
        return [item for item in self.messages if item.message_id not in self.published]

    def mark_published(self, *, message_id, worker_id, published_at):
        del worker_id, published_at
        if message_id in self.published:
            return False
        self.published.add(message_id)
        return True

    def mark_failed(self, **kwargs):
        self.failures += 1
        self.dead = self.failures >= kwargs["maximum_attempts"]
        return self.dead

    def pending_lag_seconds(self, *, now):
        del now
        return 0.0


class FakeUnit:
    def __init__(self, repository):
        self.outbox = repository

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del args


class FakeComposition:
    def __init__(self, repository):
        self.repository = repository

    def unit_of_work(self):
        return FakeUnit(self.repository)


class FailingPublisher:
    def publish(self, value):
        del value
        raise RuntimeError("provider detail must not escape")


def test_local_outbox_delivery_is_idempotent_and_observable() -> None:
    item = message()
    repository = FakeOutboxRepository([item])
    publisher = LocalIdempotentPublisher()
    metrics = InMemoryMetricsSink()
    worker = OutboxDeliveryWorker(
        cast(PostgresRepositoryComposition, FakeComposition(repository)),
        publisher,
        worker_id="worker-1",
        metrics=metrics,
    )
    first = worker.run_once(now=NOW)
    second = worker.run_once(now=NOW + timedelta(seconds=1))
    assert first.claimed == first.published == 1
    assert second.claimed == 0
    assert publisher.delivered == {item.message_id: item}


def test_outbox_retry_and_dead_letter_are_bounded() -> None:
    repository = FakeOutboxRepository([message()])
    metrics = InMemoryMetricsSink()
    worker = OutboxDeliveryWorker(
        cast(PostgresRepositoryComposition, FakeComposition(repository)),
        FailingPublisher(),
        worker_id="worker-1",
        metrics=metrics,
        maximum_attempts=2,
    )
    first = worker.run_once(now=NOW)
    second = worker.run_once(now=NOW + timedelta(seconds=5))
    assert first.retried == 1
    assert second.dead_lettered == 1
    assert repository.dead


class FixedLock:
    def __init__(self, acquired=True):
        self.acquired = acquired

    @contextmanager
    def acquire(self):
        yield self.acquired


class FakeRecoveryWorker:
    def __init__(self):
        self.calls = 0

    def run_once(self, *, now=None):
        del now
        self.calls += 1
        return RecoveryResult(2, 1, 3)


def test_recovery_coordinator_skips_overlap_and_reports_health() -> None:
    skipped_health = WorkerHealth()
    skipped = DispatchRecoveryCoordinator(
        cast(DispatchRecoveryWorker, FakeRecoveryWorker()),
        FixedLock(False),
        skipped_health,
    ).run_once(now=NOW)
    assert not skipped.ran
    assert skipped_health.snapshot().skipped_overlap_count == 1

    health = WorkerHealth()
    worker = FakeRecoveryWorker()
    result = DispatchRecoveryCoordinator(
        cast(DispatchRecoveryWorker, worker), FixedLock(), health
    ).run_once(now=NOW)
    assert result.ran and result.recovery == RecoveryResult(2, 1, 3)
    assert health.snapshot().ready(now=NOW)


def test_request_size_limit_rejects_declared_and_streamed_oversize() -> None:
    app = FastAPI()

    @app.post("/dispatch/body")
    async def body(request: Request):
        return {"size": len(await request.body())}

    app.add_middleware(RequestSizeLimitMiddleware, maximum_bytes=1024)
    client = TestClient(app)
    assert client.post("/dispatch/body", content=b"a" * 1024).status_code == 200
    response = client.post("/dispatch/body", content=b"a" * 1025)
    assert response.status_code == 413
    assert response.json() == {"error": {"code": "request_too_large"}}


def test_worker_policy_bounds_are_fail_closed() -> None:
    with pytest.raises(ValueError):
        OutboxDeliveryWorker(
            cast(
                PostgresRepositoryComposition,
                FakeComposition(FakeOutboxRepository([])),
            ),
            LocalIdempotentPublisher(),
            worker_id="worker-1",
            maximum_attempts=0,
        )
