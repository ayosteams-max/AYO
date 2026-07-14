from decimal import Decimal

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.repositories.memory import (
    InMemoryLegacyWalletRepository,
    InMemoryRideRepository,
)
from BACKEND.schemas.ride import RideRequest
from BACKEND.services.ride_service import create_ride
from BACKEND.services.wallet_service import add_trip_earning


def sample_ride() -> Ride:
    return Ride(
        ride_id="TEST-RIDE",
        rider_name="Test Rider",
        pickup="Test Pickup",
        destination="Test Destination",
        ride_type="standard",
        status=RideStatus.WAITING_FOR_DRIVER,
        driver_queue=[{"driver_id": "TEST-DRIVER", "offer_status": "QUEUED"}],
    )


def test_ride_repository_returns_isolated_aggregates():
    repository = InMemoryRideRepository()
    original = sample_ride()

    stored = repository.save(original)
    stored.status = RideStatus.TRIP_COMPLETED
    stored.driver_queue[0]["offer_status"] = "CHANGED"

    persisted = repository.get(original.ride_id)
    assert persisted is not None
    assert persisted.status == RideStatus.WAITING_FOR_DRIVER
    assert persisted.driver_queue[0]["offer_status"] == "QUEUED"


def test_ride_repository_status_contract_handles_found_and_missing_records():
    repository = InMemoryRideRepository()
    repository.save(sample_ride())

    updated = repository.update_status("TEST-RIDE", RideStatus.DRIVER_ACCEPTED)

    assert updated is not None
    assert updated.status == RideStatus.DRIVER_ACCEPTED
    assert repository.update_status("MISSING", RideStatus.DRIVER_ACCEPTED) is None


def test_ride_service_uses_injected_repository():
    repository = InMemoryRideRepository()
    request = RideRequest(
        rider_name="Test Rider",
        pickup="Test Pickup",
        destination="Test Destination",
        pickup_latitude=8.9806,
        pickup_longitude=38.7578,
    )

    response = create_ride(request, repository)

    persisted = repository.get(response.ride_id)
    assert persisted is not None
    assert persisted.status.value == response.status


def test_wallet_repository_and_service_do_not_share_mutable_records():
    repository = InMemoryLegacyWalletRepository()

    result = add_trip_earning(
        "TEST-DRIVER",
        "TEST-RIDE",
        "100.05",
        "CARD",
        repository=repository,
    )
    result["wallet"]["digital_balance"] = Decimal("999999.00")
    result["wallet"]["transactions"].clear()

    persisted = repository.get("TEST-DRIVER")
    assert persisted is not None
    assert persisted["digital_balance"] == Decimal("85.04")
    assert len(persisted["transactions"]) == 1
