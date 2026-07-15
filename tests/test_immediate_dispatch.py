from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from BACKEND.dispatch.contracts import DispatchConflict, IdempotencyConflict
from BACKEND.dispatch.memory import InMemoryDispatchRepository
from BACKEND.dispatch.models import (
    CreateRideCommand,
    DispatchPolicy,
    DriverAvailability,
    DriverCandidate,
    DriverReputation,
    PlaceSnapshot,
    QuoteSnapshot,
    RideState,
)
from BACKEND.dispatch.scoring import score_candidates
from BACKEND.dispatch.service import ImmediateDispatchService, QuoteExpired

NOW = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
RIDER_ID = UUID("10000000-0000-4000-8000-000000000001")


def command(*, destination: str = "place-destination-0001") -> CreateRideCommand:
    return CreateRideCommand(
        pickup=PlaceSnapshot(
            place_id="place-pickup-0000001", display_name="Verified pickup"
        ),
        destination=PlaceSnapshot(
            place_id=destination, display_name="Verified destination"
        ),
        service_type="ayo_go",
        quote=QuoteSnapshot(
            quote_id=uuid4(),
            amount_minor=18_000,
            currency="ETB",
            pricing_version="pricing.test.v1",
            expires_at=NOW + timedelta(minutes=5),
        ),
    )


def candidate(
    eta: int,
    *,
    driver_id: UUID | None = None,
    verified: bool = True,
    safe: bool = True,
    opportunity: str = "0",
    completed: int = 0,
    reliable: int = 0,
) -> DriverCandidate:
    return DriverCandidate(
        driver_id=driver_id or uuid4(),
        availability=DriverAvailability.AVAILABLE,
        verified=verified,
        safety_eligible=safe,
        service_types=frozenset({"ayo_go"}),
        pickup_eta_seconds=eta,
        location_observed_at=NOW,
        opportunity_deficit=Decimal(opportunity),
        reputation=DriverReputation(
            completed_trips=completed,
            reliable_completions=reliable,
        ),
    )


def service(
    *drivers: DriverCandidate,
) -> tuple[ImmediateDispatchService, InMemoryDispatchRepository]:
    repository = InMemoryDispatchRepository(list(drivers))
    policy = DispatchPolicy(version="dispatch.test.v1")
    return ImmediateDispatchService(repository, policy), repository


def create(
    dispatch: ImmediateDispatchService,
    *,
    rider_id: UUID = RIDER_ID,
    key: str = "test-idempotency-key-0001",
    request: CreateRideCommand | None = None,
):
    return dispatch.create_ride(
        rider_id=rider_id,
        idempotency_key=key,
        command=request or command(),
        now=NOW,
    )


def test_server_authoritative_creation_is_idempotent_and_audited() -> None:
    dispatch, repository = service()
    request = command()

    first, first_created = create(dispatch, request=request)
    repeated, repeated_created = create(dispatch, request=request)

    assert first_created is True
    assert repeated_created is False
    assert repeated == first
    assert first.state == RideState.SEARCHING
    assert first.accepted_at == NOW
    assert first.estimated_fare_minor == 18_000
    assert len(str(first.ride_id)) == 36
    assert len(repository.audit_events) == 1
    assert repository.audit_events[0].safe_metadata == {
        "operation": "create",
        "state_to": "searching",
        "policy_version": "dispatch.test.v1",
    }
    assert "pickup" not in str(repository.audit_events[0].safe_metadata)


def test_idempotency_key_conflict_and_active_ride_conflict_are_rejected() -> None:
    dispatch, _ = service()
    create(dispatch)

    with pytest.raises(IdempotencyConflict):
        create(dispatch, request=command(destination="place-destination-0002"))
    with pytest.raises(DispatchConflict):
        create(dispatch, key="test-idempotency-key-0002")


def test_expired_quote_is_rejected_before_ride_creation() -> None:
    dispatch, repository = service()
    expired = command().model_copy(
        update={
            "quote": command().quote.model_copy(
                update={"expires_at": NOW - timedelta(seconds=1)}
            )
        }
    )

    with pytest.raises(QuoteExpired):
        create(dispatch, request=expired)
    assert repository.get_active_ride_for_rider(RIDER_ID) is None


def test_scoring_filters_unsafe_unverified_and_stale_candidates() -> None:
    fastest_unsafe = candidate(60, safe=False)
    unverified = candidate(70, verified=False)
    valid = candidate(100)
    stale = candidate(80).model_copy(
        update={"location_observed_at": NOW - timedelta(minutes=2)}
    )
    dispatch, repository = service(fastest_unsafe, unverified, valid, stale)
    ride, _ = create(dispatch)

    offer = dispatch.dispatch_next(ride.ride_id, now=NOW)

    assert offer is not None
    assert offer.driver_id == valid.driver_id
    assert offer.score.reason_codes == (
        "fast_pickup",
        "eligible",
        "policy_versioned",
        "neutral_reputation",
    )
    assert len(repository.audit_events) == 2


def test_new_driver_has_neutral_trust_and_no_hidden_penalty() -> None:
    new_driver = candidate(90, completed=0)
    sparse_history = candidate(90, completed=19, reliable=0)
    dispatch, repository = service(new_driver, sparse_history)
    ride, _ = create(dispatch)
    aggregate = repository.get_ride(ride.ride_id)
    assert aggregate is not None

    scores = score_candidates(
        aggregate,
        [new_driver, sparse_history],
        DispatchPolicy(version="dispatch.test.v1"),
        NOW,
    )

    assert {score.trust_score for score in scores} == {Decimal("0.5000")}
    assert all(score.neutral_reputation for score in scores)
    assert all(score.reliability_penalty_seconds == 0 for score in scores)


def test_fairness_is_bounded_by_pickup_eta_guardrail() -> None:
    fastest = candidate(100, opportunity="0")
    equivalent_waiting_driver = candidate(115, opportunity="1")
    too_slow = candidate(121, opportunity="1")
    dispatch, repository = service(fastest, equivalent_waiting_driver, too_slow)
    ride, _ = create(dispatch)
    aggregate = repository.get_ride(ride.ride_id)
    assert aggregate is not None

    scores = score_candidates(
        aggregate,
        [fastest, equivalent_waiting_driver, too_slow],
        DispatchPolicy(version="dispatch.test.v1"),
        NOW,
    )

    assert scores[0].driver_id == equivalent_waiting_driver.driver_id
    assert scores[0].fairness_credit_seconds == 20
    assert too_slow.driver_id not in {score.driver_id for score in scores}


def test_decline_automatically_reassigns_without_rematching_same_driver() -> None:
    first = candidate(60)
    second = candidate(90)
    dispatch, repository = service(first, second)
    ride, _ = create(dispatch)
    offer = dispatch.dispatch_next(ride.ride_id, now=NOW)
    assert offer is not None and offer.driver_id == first.driver_id

    replacement = dispatch.decline_and_reassign(
        offer.offer_id, first.driver_id, now=NOW + timedelta(seconds=2)
    )

    assert replacement is not None
    assert replacement.driver_id == second.driver_id
    updated = repository.get_ride(ride.ride_id)
    assert updated is not None
    assert first.driver_id in updated.attempted_driver_ids
    assert [event.action for event in repository.audit_events] == [
        "dispatch.ride.create",
        "dispatch.offer.create",
        "dispatch.offer.decline",
        "dispatch.offer.create",
    ]


def test_offer_timeout_requires_server_time_then_reassigns() -> None:
    first = candidate(60)
    second = candidate(75)
    dispatch, _ = service(first, second)
    ride, _ = create(dispatch)
    offer = dispatch.dispatch_next(ride.ride_id, now=NOW)
    assert offer is not None

    with pytest.raises(DispatchConflict):
        dispatch.expire_and_reassign(
            offer.offer_id, now=offer.expires_at - timedelta(milliseconds=1)
        )
    replacement = dispatch.expire_and_reassign(offer.offer_id, now=offer.expires_at)
    assert replacement is not None
    assert replacement.driver_id == second.driver_id


def test_offer_acceptance_checks_driver_and_is_retry_safe() -> None:
    driver = candidate(60)
    dispatch, repository = service(driver)
    ride, _ = create(dispatch)
    offer = dispatch.dispatch_next(ride.ride_id, now=NOW)
    assert offer is not None

    with pytest.raises(DispatchConflict):
        dispatch.accept_offer(offer.offer_id, uuid4(), now=NOW)
    accepted = dispatch.accept_offer(offer.offer_id, driver.driver_id, now=NOW)
    repeated = dispatch.accept_offer(offer.offer_id, driver.driver_id, now=NOW)

    assert accepted == repeated
    assert accepted.state == RideState.ASSIGNED
    assert accepted.assigned_driver_id == driver.driver_id
    assert (
        len(
            [
                event
                for event in repository.audit_events
                if event.action == "dispatch.offer.accept"
            ]
        )
        == 1
    )


def test_concurrent_rides_cannot_reserve_one_driver_twice() -> None:
    driver = candidate(60)
    dispatch, _ = service(driver)
    first_ride, _ = create(dispatch)
    second_ride, _ = create(
        dispatch,
        rider_id=uuid4(),
        key="test-idempotency-key-0003",
        request=command(destination="place-destination-0003"),
    )

    def attempt(ride_id: UUID):
        try:
            return dispatch.dispatch_next(ride_id, now=NOW)
        except DispatchConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [first_ride.ride_id, second_ride.ride_id]))

    assert sum(item is not None for item in outcomes) == 1


def test_network_recovery_returns_authoritative_active_projection() -> None:
    dispatch, _ = service()
    created, _ = create(dispatch)

    recovered = dispatch.recover_active_ride(RIDER_ID)

    assert recovered == created
    assert dispatch.recover_active_ride(uuid4()) is None


def test_no_candidates_is_honest_and_audited_without_fake_assignment() -> None:
    dispatch, repository = service()
    ride, _ = create(dispatch)

    assert dispatch.dispatch_next(ride.ride_id, now=NOW) is None
    recovered = repository.get_ride(ride.ride_id)
    assert recovered is not None
    assert recovered.state == RideState.NO_DRIVER_AVAILABLE
    assert recovered.assigned_driver_id is None
    assert dispatch.recover_active_ride(RIDER_ID) is None
    assert repository.audit_events[-1].reason == "no_eligible_driver"


def test_recovery_sweep_expires_and_reassigns_bounded_offers() -> None:
    first = candidate(60)
    second = candidate(80)
    dispatch, _ = service(first, second)
    ride, _ = create(dispatch)
    offer = dispatch.dispatch_next(ride.ride_id, now=NOW)
    assert offer is not None

    assert dispatch.recover_expired_offers(now=offer.expires_at, limit=10) == 1
    recovered = dispatch.recover_active_ride(RIDER_ID)
    assert recovered is not None
    assert recovered.state == RideState.OFFERING
    assert dispatch.recover_expired_offers(now=offer.expires_at, limit=10) == 0
