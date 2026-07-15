from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import AssuranceLevel, IdentityType
from BACKEND.persistence.tables import (
    audit_events,
    dispatch_outbox,
    reservation_idempotency_records,
    reservation_state_history,
    ride_reservations,
)
from BACKEND.scheduled.application import ScheduledRideApplication
from BACKEND.scheduled.engine import (
    DeterministicScheduledStrategy,
    ReservationConflict,
    evaluate_pre_dispatch,
    should_replace_soft_candidate,
)
from BACKEND.scheduled.integration import (
    LocalVerifiedPassengerResolver,
    ScheduledIntegrationApplication,
)
from BACKEND.scheduled.integration_models import (
    CreateScheduledReservationCommand,
    PassengerChannel,
    UpdateReservationCommand,
)
from BACKEND.scheduled.models import (
    CandidateDecision,
    PreDispatchState,
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)
SECRET = b"mission-17-local-test-secret-32bytes-minimum"


def subject(identity_type=IdentityType.RIDER, *, identity_id=None, mfa=True):
    actor = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.DRIVER: ActorType.DRIVER,
        IdentityType.STAFF: ActorType.STAFF,
    }[identity_type]
    return AuthorizationSubject(
        identity_id=identity_id or uuid4(),
        identity_type=identity_type,
        actor_type=actor,
        assurance_level=(AssuranceLevel.MULTI_FACTOR if mfa else AssuranceLevel.BASIC),
    )


def command(*, contact="contact:verified:passenger-0001"):
    return CreateScheduledReservationCommand(
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="ayo.go",
        quote_id=uuid4(),
        requested_pickup_at=NOW + timedelta(days=2),
        requested_timezone="Africa/Addis_Ababa",
        passenger_channel=PassengerChannel.VERIFIED_CONTACT,
        passenger_contact_reference=contact,
        future_payer_reference="payer:future:separate-0001",
    )


def candidate(driver_id, **changes):
    values = {
        "driver_id": driver_id,
        "eligible": True,
        "safety_eligible": True,
        "pickup_eta_low_seconds": 240,
        "pickup_eta_high_seconds": 360,
        "pickup_window_success_bps": 9000,
        "recovery_capacity_bps": 8500,
        "prediction_confidence_bps": 9000,
        "location_observed_at": NOW,
    }
    values.update(changes)
    return ScheduledCandidate(**values)


def app(composition, passenger, contact="contact:verified:passenger-0001"):
    policy = ReservationPolicy(version="scheduled.v1")
    return ScheduledIntegrationApplication(
        composition,
        policy,
        pickup_secret=SECRET,
        passenger_resolver=LocalVerifiedPassengerResolver(
            {contact: passenger.identity_id}
        ),
    ), policy


def test_postgres_third_party_end_to_end_is_atomic_and_public(
    postgres_engine, postgres_composition
) -> None:
    booker, passenger, driver = subject(), subject(), subject(IdentityType.DRIVER)
    integration, policy = app(postgres_composition, passenger)
    created, fresh = integration.create(
        booker, command(), idempotency_key="mission17-create-0001", now=NOW
    )
    assert fresh and created.state == "passenger_confirmation_pending"
    confirmed = integration.confirm_or_decline(
        passenger,
        created.reservation_id,
        confirmed=True,
        now=NOW + timedelta(minutes=1),
    )
    assert confirmed.state == "accepted"

    with postgres_composition.unit_of_work() as unit:
        stored = unit.scheduled.get(created.reservation_id)
        assert stored is not None
        planning = unit.scheduled.mutate(
            stored,
            expected_version=stored.version,
            state=ReservationState.PLANNING,
            values=None,
            audit_event=_system_audit(stored, "reservation.planning_started"),
            event_type="reservation.updated",
            reason="planning_checkpoint",
            now=NOW + timedelta(minutes=2),
        )
        decisions = DeterministicScheduledStrategy(policy).rank(
            planning, [candidate(driver.identity_id)], now=NOW + timedelta(minutes=2)
        )
        scheduled = ScheduledRideApplication(
            unit.scheduled, DeterministicScheduledStrategy(policy), policy
        )
        planned = scheduled.plan(
            planning, [candidate(driver.identity_id)], now=NOW + timedelta(minutes=2)
        )
        committed = scheduled.commit(
            planned, decisions[0], now=NOW + timedelta(minutes=3)
        )
        assert committed.state is ReservationState.DRIVER_COMMITTED

    accepted = integration.driver_commitment_response(
        driver,
        created.reservation_id,
        accepted=True,
        expected_version=committed.version,
        now=NOW + timedelta(minutes=4),
    )
    assert accepted.state == "driver_committed"
    with postgres_composition.unit_of_work() as unit:
        current = unit.scheduled.get(created.reservation_id)
        assert current is not None
        projection = evaluate_pre_dispatch(
            current,
            candidate(driver.identity_id, current_trip_completion_high_seconds=600),
            policy,
        )
    assert projection.state is PreDispatchState.PROVISIONAL
    en_route = integration.driver_progress(
        driver, created.reservation_id, ready=False, now=NOW + timedelta(minutes=5)
    )
    ready = integration.driver_progress(
        driver, created.reservation_id, ready=True, now=NOW + timedelta(minutes=6)
    )
    assert en_route.state == "driver_en_route" and ready.state == "ready_for_pickup"
    integration.create_pickup_code(created.reservation_id, "123456", now=NOW)
    activated = integration.verify_pickup(
        driver, created.reservation_id, "123456", now=NOW + timedelta(minutes=7)
    )
    assert activated.state == "activated_as_ride"
    assert not hasattr(activated, "effective_reliability_bps")

    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(audit_events)
            ).scalar_one()
            >= 7
        )
        assert (
            connection.execute(
                select(func.count()).select_from(dispatch_outbox)
            ).scalar_one()
            >= 7
        )
        assert (
            connection.execute(
                select(func.count()).select_from(reservation_state_history)
            ).scalar_one()
            >= 5
        )


def _system_audit(item, action):
    from BACKEND.audit.models import AuditEvent, AuditOutcome

    return AuditEvent(
        actor_type=ActorType.SYSTEM,
        action=action,
        resource_type="scheduled_reservation",
        resource_id=str(item.reservation_id),
        outcome=AuditOutcome.SUCCESS,
        reason="checkpoint",
        correlation_id=uuid4(),
        source_module="scheduled",
    )


def test_atomic_idempotency_and_concurrent_creation(
    postgres_engine, postgres_composition
):
    booker, passenger = subject(), subject()
    integration, _ = app(postgres_composition, passenger)
    request = command()

    def create():
        return integration.create(
            booker, request, idempotency_key="mission17-concurrent-key", now=NOW
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sum(created for _, created in results) == 1
    assert results[0][0].reservation_id == results[1][0].reservation_id
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(ride_reservations)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count()).select_from(reservation_idempotency_records)
            ).scalar_one()
            == 1
        )


def test_conflicting_driver_commitment_is_prevented_by_postgres(postgres_composition):
    first_booker, second_booker, passenger = subject(), subject(), subject()
    integration, policy = app(postgres_composition, passenger)
    self_request = command().model_copy(
        update={
            "passenger_channel": PassengerChannel.IDENTITY,
            "passenger_contact_reference": None,
        }
    )
    first, _ = integration.create(
        first_booker, self_request, idempotency_key="conflict-first-0001", now=NOW
    )
    second_request = self_request
    second_request = second_request.model_copy(update={"quote_id": uuid4()})
    second, _ = integration.create(
        second_booker, second_request, idempotency_key="conflict-second-001", now=NOW
    )
    driver = uuid4()

    def commit(reservation_id):
        try:
            with postgres_composition.unit_of_work() as unit:
                item = unit.scheduled.get(reservation_id)
                assert item is not None
                planning = unit.scheduled.mutate(
                    item,
                    expected_version=item.version,
                    state=ReservationState.PLANNING,
                    values=None,
                    audit_event=_system_audit(item, "reservation.planning_started"),
                    event_type="reservation.updated",
                    reason="planning",
                    now=NOW,
                )
                decision = DeterministicScheduledStrategy(policy).rank(
                    planning, [candidate(driver)], now=NOW
                )[0]
                ScheduledRideApplication(
                    unit.scheduled, DeterministicScheduledStrategy(policy), policy
                ).commit(planning, decision, now=NOW)
            return True
        except ReservationConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [first.reservation_id, second.reservation_id]))
    assert sum(outcomes) == 1


def test_step_up_update_and_rollback(postgres_engine, postgres_composition):
    booker, passenger = subject(mfa=False), subject()
    integration, _ = app(postgres_composition, passenger)
    created, _ = integration.create(
        booker, command(), idempotency_key="step-up-create-0001", now=NOW
    )
    with pytest.raises(ReservationConflict, match="Step-up"):
        integration.update(
            booker,
            created.reservation_id,
            UpdateReservationCommand(
                expected_version=created.version,
                destination_place_id="place.addis.megenagna",
            ),
            now=NOW,
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(ride_reservations.c.destination_place_id).where(
                    ride_reservations.c.reservation_id == created.reservation_id
                )
            ).scalar_one()
            == "place.addis.saris"
        )


def test_material_replacement_and_marginal_suppression_are_deterministic():
    policy = ReservationPolicy(version="scheduled.v1")
    # Same deterministic inputs replay to the same replacement outcome.
    incumbent = CandidateDecision(
        driver_id=uuid4(),
        policy_version=policy.version,
        conservative_eta_seconds=900,
        reliability_bps=8000,
        fairness_credit_bps=0,
        effective_reliability_bps=8000,
        reason_codes=("eligible",),
    )
    marginal = incumbent.model_copy(
        update={
            "driver_id": uuid4(),
            "conservative_eta_seconds": 750,
            "effective_reliability_bps": 9500,
        }
    )
    material = incumbent.model_copy(
        update={
            "driver_id": uuid4(),
            "conservative_eta_seconds": 300,
            "effective_reliability_bps": 9500,
        }
    )
    from BACKEND.scheduled.models import ScheduledReservation

    item = ScheduledReservation(
        booker_id=uuid4(),
        passenger_participant_id=uuid4(),
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="ayo.go",
        quote_id=uuid4(),
        requested_pickup_at=NOW + timedelta(days=1),
        requested_timezone="Africa/Addis_Ababa",
        state=ReservationState.PLANNING,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        created_at=NOW,
        updated_at=NOW,
    )
    assert not should_replace_soft_candidate(incumbent, marginal, item, policy)[0]
    assert should_replace_soft_candidate(incumbent, material, item, policy)[0]
