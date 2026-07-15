from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.dispatch.application import DispatchApplication
from BACKEND.dispatch.models import (
    CreateRideCommand,
    DispatchPolicy,
    DriverAvailability,
    DriverCandidate,
    PlaceSnapshot,
    QuoteSnapshot,
    RideState,
)
from BACKEND.dispatch.worker import DispatchRecoveryWorker
from BACKEND.persistence.composition import PostgresRepositoryComposition
from BACKEND.persistence.tables import (
    audit_events,
    dispatch_driver_offers,
    dispatch_idempotency_records,
    dispatch_outbox,
    dispatch_ride_requests,
    identities,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 8, tzinfo=UTC)
RIDER_ID = UUID("10000000-0000-4000-8000-000000000001")
DRIVER_ID = UUID("20000000-0000-4000-8000-000000000001")


class FixedCandidates:
    def list_candidates(self, *, ride, now, limit):
        del ride
        return [
            DriverCandidate(
                driver_id=DRIVER_ID,
                availability=DriverAvailability.AVAILABLE,
                verified=True,
                safety_eligible=True,
                service_types=frozenset({"ayo_go"}),
                pickup_eta_seconds=90,
                location_observed_at=now - timedelta(seconds=1),
            )
        ][:limit]


@pytest.fixture
def dispatch_application(postgres_engine):
    with postgres_engine.begin() as connection:
        for identity_id, identity_type in (
            (RIDER_ID, "rider"),
            (DRIVER_ID, "driver"),
        ):
            connection.execute(
                insert(identities).values(
                    identity_id=identity_id,
                    public_id=uuid4(),
                    identity_type=identity_type,
                    status="active",
                    created_at=NOW,
                    updated_at=NOW,
                    version=1,
                )
            )
    composition = PostgresRepositoryComposition(
        postgres_engine, dispatch_candidates=FixedCandidates()
    )
    return DispatchApplication(composition, DispatchPolicy(version="dispatch.v1"))


def command() -> CreateRideCommand:
    return CreateRideCommand(
        pickup=PlaceSnapshot(place_id="pickup-0001", display_name="Bole"),
        destination=PlaceSnapshot(
            place_id="destination-0001", display_name="Meskel Square"
        ),
        service_type="ayo_go",
        quote=QuoteSnapshot(
            quote_id=uuid4(),
            amount_minor=18000,
            currency="ETB",
            pricing_version="pricing.v1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        ),
    )


def test_ride_offer_audit_and_outbox_are_durable_and_atomic(
    postgres_engine, dispatch_application
) -> None:
    ride, created = dispatch_application.create_ride(
        rider_id=RIDER_ID,
        idempotency_key="network-retry-key-0001",
        command=command(),
    )
    assert created
    offer = dispatch_application.dispatch_next(ride.ride_id)
    assert offer is not None
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_ride_requests)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_driver_offers)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_idempotency_records)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_outbox)
            ).scalar_one()
            == 2
        )


def test_concurrent_idempotent_creation_returns_one_ride(
    postgres_engine, dispatch_application
) -> None:
    request = command()

    def create():
        return dispatch_application.create_ride(
            rider_id=RIDER_ID,
            idempotency_key="concurrent-retry-key-001",
            command=request,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in [executor.submit(create), executor.submit(create)]
        ]
    assert {result[0].ride_id for result in results}.__len__() == 1
    assert sorted(result[1] for result in results) == [False, True]
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_ride_requests)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_idempotency_records)
            ).scalar_one()
            == 1
        )


def test_offer_acceptance_is_concurrent_retry_safe(
    postgres_engine, dispatch_application
) -> None:
    ride, _ = dispatch_application.create_ride(
        rider_id=RIDER_ID,
        idempotency_key="accept-retry-key-00001",
        command=command(),
    )
    offer = dispatch_application.dispatch_next(ride.ride_id)
    assert offer is not None

    with ThreadPoolExecutor(max_workers=2) as executor:
        assigned = [
            future.result()
            for future in (
                executor.submit(
                    dispatch_application.accept_offer, offer.offer_id, DRIVER_ID
                ),
                executor.submit(
                    dispatch_application.accept_offer, offer.offer_id, DRIVER_ID
                ),
            )
        ]
    assert all(result.state is RideState.ASSIGNED for result in assigned)
    assert {result.assigned_driver_id for result in assigned} == {DRIVER_ID}


def test_recovery_worker_expires_offer_and_reaches_no_driver_outcome(
    dispatch_application,
) -> None:
    ride, _ = dispatch_application.create_ride(
        rider_id=RIDER_ID,
        idempotency_key="expiry-recovery-key-01",
        command=command(),
    )
    offer = dispatch_application.dispatch_next(ride.ride_id)
    assert offer is not None
    result = DispatchRecoveryWorker(dispatch_application).run_once(
        now=offer.expires_at + timedelta(seconds=1)
    )
    assert result.expired_offers == 1
    recovered = dispatch_application.recover_ride(RIDER_ID)
    assert recovered is None
