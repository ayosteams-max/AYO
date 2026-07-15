from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import insert

from BACKEND.active_ride.models import ActiveRide, ActiveRideState
from BACKEND.active_ride.workers import ActiveRideWorker, ActiveRideWorkerKind
from BACKEND.persistence.tables import active_ride_recovery_checkpoints

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


class Processor:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def process(self, checkpoint, *, now):
        del checkpoint, now
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)


def test_worker_claim_is_bounded_restart_safe_and_overlap_is_prevented(
    postgres_engine, postgres_composition
):
    ride_id = uuid4()
    with postgres_composition.unit_of_work() as unit:
        unit.active_rides.create_from_assignment(
            ActiveRide(
                ride_id=ride_id,
                rider_id=uuid4(),
                driver_id=uuid4(),
                assignment_id=uuid4(),
                state=ActiveRideState.ASSIGNED,
                pickup_place_id="place.addis.bole",
                destination_place_id="place.addis.saris",
                service_type="ayo.go",
                created_at=NOW,
                updated_at=NOW,
                last_sequence=1,
            )
        )
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(active_ride_recovery_checkpoints).values(
                checkpoint_id=uuid4(),
                ride_id=ride_id,
                kind=ActiveRideWorkerKind.STALE_RIDE.value,
                due_at=NOW,
                attempt_count=0,
                payload={},
                created_at=NOW,
            )
        )
    processor = Processor()
    first = ActiveRideWorker(
        postgres_engine,
        ActiveRideWorkerKind.STALE_RIDE,
        processor,
        worker_id="active-worker-a",
        batch_limit=1,
    )
    second = ActiveRideWorker(
        postgres_engine,
        ActiveRideWorkerKind.STALE_RIDE,
        processor,
        worker_id="active-worker-b",
        batch_limit=1,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(first.run_once, now=NOW)
        assert processor.started.wait(timeout=5)
        overlap = second.run_once(now=NOW)
        processor.release.set()
        completed = running.result(timeout=5)
    assert overlap.ran is False
    assert completed.completed == 1
    assert processor.calls == 1
    assert first.run_once(now=NOW).claimed == 0
