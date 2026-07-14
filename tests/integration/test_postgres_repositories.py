from decimal import Decimal

import pytest
from sqlalchemy import select

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.health import DatabaseHealthChecker
from BACKEND.persistence.tables import rides

pytestmark = pytest.mark.integration


def sample_ride(ride_id: str = "TEST-RIDE") -> Ride:
    return Ride(
        ride_id=ride_id,
        rider_name="Test Rider",
        pickup="Test Pickup",
        destination="Test Destination",
        ride_type="standard",
        status=RideStatus.WAITING_FOR_DRIVER,
        driver_id="TEST-DRIVER",
        driver_queue=[{"driver_id": "TEST-DRIVER", "offer_status": "QUEUED"}],
    )


def test_postgres_ride_repository_contract_and_database_fields(
    postgres_engine, postgres_composition
):
    with postgres_composition.unit_of_work() as unit_of_work:
        stored = unit_of_work.rides.save(sample_ride())
        stored.driver_queue.clear()

    with postgres_composition.unit_of_work() as unit_of_work:
        persisted = unit_of_work.rides.get("TEST-RIDE")
        assert persisted is not None
        assert len(persisted.driver_queue) == 1
        updated = unit_of_work.rides.update_status(
            "TEST-RIDE", RideStatus.DRIVER_ACCEPTED
        )
        assert updated is not None
        assert updated.status == RideStatus.DRIVER_ACCEPTED
        assert unit_of_work.rides.get("MISSING") is None

    with postgres_engine.connect() as connection:
        row = connection.execute(
            select(rides.c.id, rides.c.version, rides.c.created_at, rides.c.updated_at)
        ).one()
        assert row.id.version == 4
        assert row.version == 2
        assert row.created_at.utcoffset() is not None
        assert row.updated_at.utcoffset() is not None


def test_unit_of_work_commits_and_rolls_back(postgres_composition):
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.rides.save(sample_ride("COMMITTED"))

    with (
        pytest.raises(RuntimeError, match="force rollback"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        unit_of_work.rides.save(sample_ride("ROLLED-BACK"))
        raise RuntimeError("force rollback")

    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.rides.get("COMMITTED") is not None
        assert unit_of_work.rides.get("ROLLED-BACK") is None


def test_optimistic_concurrency_detects_stale_aggregate(postgres_composition):
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.rides.save(sample_ride())

    first = postgres_composition.unit_of_work()
    second = postgres_composition.unit_of_work()
    with first, second:
        first_ride = first.rides.get("TEST-RIDE")
        second_ride = second.rides.get("TEST-RIDE")
        assert first_ride is not None
        assert second_ride is not None

        first_ride.status = RideStatus.DRIVER_ACCEPTED
        first.rides.save(first_ride)
        first.commit()

        second_ride.status = RideStatus.DRIVER_DECLINED
        with pytest.raises(OptimisticConcurrencyError):
            second.rides.save(second_ride)
        second.rollback()


def test_legacy_wallet_round_trip_preserves_decimals_but_is_not_a_ledger(
    postgres_composition,
):
    wallet = {
        "driver_id": "TEST-DRIVER",
        "currency": "ETB",
        "digital_balance": Decimal("85.04"),
        "transactions": [{"amount": Decimal("85.04")}],
    }
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.legacy_wallets.save(wallet)

    with postgres_composition.unit_of_work() as unit_of_work:
        stored = unit_of_work.legacy_wallets.get("TEST-DRIVER")
        assert stored == wallet


def test_database_health_probe(postgres_engine):
    result = DatabaseHealthChecker(postgres_engine).check()

    assert result.ready
    assert result.error_category is None
    assert result.latency_ms >= 0
