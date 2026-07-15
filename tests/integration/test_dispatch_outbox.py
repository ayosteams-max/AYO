from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select

from BACKEND.dispatch.outbox import LocalIdempotentPublisher
from BACKEND.dispatch.outbox_worker import OutboxDeliveryWorker
from BACKEND.observability import InMemoryMetricsSink
from BACKEND.persistence.tables import dispatch_outbox

pytestmark = pytest.mark.integration


def seed_message(postgres_engine, *, occurred_at=None):
    now = occurred_at or datetime.now(UTC)
    message_id = uuid4()
    ride_id = uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(dispatch_outbox).values(
                message_id=message_id,
                aggregate_type="ride",
                aggregate_id=ride_id,
                event_type="dispatch.ride.requested",
                payload={"ride_id": str(ride_id)},
                occurred_at=now,
                available_at=now,
                attempt_count=0,
            )
        )
    return message_id


def test_concurrent_outbox_workers_claim_one_logical_delivery(
    postgres_engine, postgres_composition
) -> None:
    message_id = seed_message(postgres_engine)
    publisher = LocalIdempotentPublisher()

    def run(worker_id):
        return OutboxDeliveryWorker(
            postgres_composition,
            publisher,
            worker_id=worker_id,
        ).run_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in (
                executor.submit(run, "worker-1"),
                executor.submit(run, "worker-2"),
            )
        ]
    assert sum(item.published for item in results) == 1
    assert set(publisher.delivered) == {message_id}
    with postgres_engine.connect() as connection:
        stored = (
            connection.execute(
                select(dispatch_outbox).where(
                    dispatch_outbox.c.message_id == message_id
                )
            )
            .mappings()
            .one()
        )
    assert stored["published_at"] is not None
    assert stored["dead_lettered_at"] is None


class FailingPublisher:
    def publish(self, message):
        del message
        raise RuntimeError("simulated provider outage")


def test_outbox_backoff_retry_and_dead_letter_survive_restart(
    postgres_engine, postgres_composition
) -> None:
    start = datetime.now(UTC)
    message_id = seed_message(postgres_engine, occurred_at=start)
    metrics = InMemoryMetricsSink()

    def new_worker():
        return OutboxDeliveryWorker(
            postgres_composition,
            FailingPublisher(),
            worker_id="restart-worker",
            metrics=metrics,
            maximum_attempts=2,
            base_backoff_seconds=5,
            maximum_backoff_seconds=20,
        )

    first = new_worker().run_once(now=start)
    too_early = new_worker().run_once(now=start + timedelta(seconds=4))
    second = new_worker().run_once(now=start + timedelta(seconds=5))
    assert first.retried == 1
    assert too_early.claimed == 0
    assert second.dead_lettered == 1
    with postgres_engine.connect() as connection:
        stored = (
            connection.execute(
                select(dispatch_outbox).where(
                    dispatch_outbox.c.message_id == message_id
                )
            )
            .mappings()
            .one()
        )
    assert stored["attempt_count"] == 2
    assert stored["last_error_code"] == "publisher_unavailable"
    assert stored["dead_lettered_at"] is not None
