from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.scheduled.application import ScheduledRideApplication
from BACKEND.scheduled.engine import (
    DeterministicScheduledStrategy,
    ReservationConflict,
    effective_airport_pickup_time,
    evaluate_pre_dispatch,
    should_replace_soft_candidate,
    transition,
    validate_formal_replacement,
)
from BACKEND.scheduled.memory import InMemoryScheduledRepository
from BACKEND.scheduled.models import (
    AirportContext,
    CandidateDecision,
    CheckpointType,
    ConsentState,
    FlightState,
    Participant,
    ParticipantKind,
    ParticipantRole,
    PreDispatchState,
    RecoveryAction,
    ReservationCheckpoint,
    ReservationPolicy,
    ReservationState,
    ScheduledCandidate,
    ScheduledReservation,
)
from BACKEND.scheduled.recovery import recover_checkpoint

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def policy(**values: object) -> ReservationPolicy:
    return ReservationPolicy.model_validate({"version": "scheduled.v1"} | values)


def reservation(**values: object) -> ScheduledReservation:
    passenger_id = values.pop("passenger_participant_id", uuid4())
    defaults = {
        "booker_id": uuid4(),
        "passenger_participant_id": passenger_id,
        "pickup_place_id": "place.addis.bole",
        "destination_place_id": "place.addis.saris",
        "service_type": "ayo.go",
        "quote_id": uuid4(),
        "requested_pickup_at": NOW + timedelta(days=2),
        "requested_timezone": "Africa/Addis_Ababa",
        "state": ReservationState.ACCEPTED,
        "policy_id": uuid4(),
        "policy_version": "scheduled.v1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(values)
    return ScheduledReservation.model_validate(defaults)


def candidate(**values: object) -> ScheduledCandidate:
    defaults = {
        "driver_id": uuid4(),
        "eligible": True,
        "safety_eligible": True,
        "pickup_eta_low_seconds": 300,
        "pickup_eta_high_seconds": 420,
        "pickup_window_success_bps": 9000,
        "recovery_capacity_bps": 8000,
        "location_observed_at": NOW,
    }
    defaults.update(values)
    return ScheduledCandidate.model_validate(defaults)


def decision(**values: object) -> CandidateDecision:
    defaults = {
        "driver_id": uuid4(),
        "policy_version": "scheduled.v1",
        "conservative_eta_seconds": 600,
        "reliability_bps": 8000,
        "fairness_credit_bps": 0,
        "effective_reliability_bps": 8000,
        "reason_codes": ("eligible",),
    }
    defaults.update(values)
    return CandidateDecision.model_validate(defaults)


def participants(item: ScheduledReservation, *, third_party: bool = False):
    passenger_identity = uuid4() if third_party else item.booker_id
    passenger = Participant(
        participant_id=item.passenger_participant_id,
        role=ParticipantRole.PASSENGER,
        kind=ParticipantKind.IDENTITY,
        identity_id=passenger_identity,
        consent_state=ConsentState.PENDING
        if third_party
        else ConsentState.NOT_REQUIRED,
    )
    booker = Participant(
        role=ParticipantRole.BOOKER,
        kind=ParticipantKind.IDENTITY,
        identity_id=item.booker_id,
    )
    return booker, passenger


def test_strategy_is_deterministic_and_bounded_fairness_breaks_equivalent_eta() -> None:
    first, second = (
        candidate(opportunity_deficit_bps=0),
        candidate(pickup_eta_high_seconds=450, opportunity_deficit_bps=600),
    )
    strategy = DeterministicScheduledStrategy(policy())
    item = reservation()
    ranked = strategy.rank(item, [first, second], now=NOW)
    assert ranked[0].driver_id == second.driver_id
    assert ranked == strategy.rank(item, [first, second], now=NOW)
    assert "bounded_opportunity_fairness" in ranked[0].reason_codes


def test_strategy_hard_filters_safety_conflicts_confidence_and_airport() -> None:
    blocked = [
        candidate(safety_eligible=False),
        candidate(has_conflicting_commitment=True),
        candidate(prediction_confidence_bps=100),
        candidate(airport_eligible=False),
    ]
    airport = AirportContext(
        airport_code="ADD",
        pickup_zone_code="bole.arrivals",
        observed_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        provider_version="manual.v1",
    )
    assert (
        DeterministicScheduledStrategy(policy()).rank(
            reservation(), blocked, now=NOW, airport_context=airport
        )
        == []
    )


def test_soft_replacement_requires_material_gain_and_stability() -> None:
    incumbent = decision()
    marginal = decision(conservative_eta_seconds=450, effective_reliability_bps=9500)
    material = decision(conservative_eta_seconds=200, effective_reliability_bps=9500)
    assert not should_replace_soft_candidate(
        incumbent, marginal, reservation(), policy()
    )[0]
    assert should_replace_soft_candidate(incumbent, material, reservation(), policy())[
        0
    ]


def test_formal_commitment_lock_and_typed_replacement_rules() -> None:
    item = reservation(active_commitment_id=uuid4())
    assert not should_replace_soft_candidate(decision(), decision(), item, policy())[0]
    assert validate_formal_replacement(item, "vehicle_breakdown", policy())[0]
    assert not validate_formal_replacement(item, "slightly_closer_driver", policy())[0]


def test_predispatch_protects_current_trip_and_releases_low_confidence() -> None:
    item = reservation()
    projection = evaluate_pre_dispatch(
        item, candidate(current_trip_completion_high_seconds=900), policy()
    )
    assert projection.state is PreDispatchState.PROVISIONAL
    assert "no_current_trip_diversion" in projection.reason_codes
    assert (
        evaluate_pre_dispatch(
            item, candidate(prediction_confidence_bps=100), policy()
        ).state
        is PreDispatchState.RELEASED
    )


def test_airport_context_uses_fresh_estimate_and_stale_safe_fallback() -> None:
    item = reservation()
    estimated = NOW + timedelta(hours=4)
    context = AirportContext(
        airport_code="ADD",
        pickup_zone_code="bole.arrivals",
        estimated_arrival_at=estimated,
        observed_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        provider_version="flight.v1",
    )
    assert effective_airport_pickup_time(item, context, now=NOW)[0] == estimated
    stale = context.model_copy(update={"expires_at": NOW - timedelta(seconds=1)})
    assert (
        effective_airport_pickup_time(item, stale, now=NOW)[0]
        == item.requested_pickup_at
    )
    with pytest.raises(ReservationConflict):
        effective_airport_pickup_time(
            item,
            context.model_copy(update={"flight_state": FlightState.CANCELLED}),
            now=NOW,
        )


def test_third_party_booking_requires_consent_and_is_idempotent() -> None:
    repo = InMemoryScheduledRepository()
    app = ScheduledRideApplication(
        repo, DeterministicScheduledStrategy(policy()), policy()
    )
    item = reservation(state=ReservationState.PASSENGER_CONFIRMATION_PENDING)
    people = participants(item, third_party=True)
    created, fresh = app.create(
        item, people, idempotency_key="request-key-123", now=NOW
    )
    replay, replay_fresh = app.create(
        item, people, idempotency_key="request-key-123", now=NOW
    )
    assert fresh and not replay_fresh and replay == created
    assert repo.audit_events[0].reason == "third_party"


def test_idempotency_key_reuse_with_different_request_is_rejected() -> None:
    repo = InMemoryScheduledRepository()
    app = ScheduledRideApplication(
        repo, DeterministicScheduledStrategy(policy()), policy()
    )
    item = reservation()
    app.create(item, participants(item), idempotency_key="request-key-123", now=NOW)
    changed = item.model_copy(update={"destination_place_id": "place.addis.megenagna"})
    with pytest.raises(ReservationConflict):
        app.create(
            changed, participants(changed), idempotency_key="request-key-123", now=NOW
        )


def test_concurrent_commit_allows_one_winner() -> None:
    repo = InMemoryScheduledRepository()
    app = ScheduledRideApplication(
        repo, DeterministicScheduledStrategy(policy()), policy()
    )
    item = reservation(state=ReservationState.PLANNING)
    repo.create(
        item,
        participants=participants(item),
        idempotency_fingerprint="x",
        request_hash="y",
        audit_event=_audit_stub(item),
    )
    choices = [decision(), decision()]

    def commit(choice):
        try:
            app.commit(item, choice, now=NOW)
            return True
        except ReservationConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(commit, choices)) == 1


def _audit_stub(item):
    from BACKEND.audit.models import ActorType, AuditEvent, AuditOutcome

    return AuditEvent(
        actor_type=ActorType.SYSTEM,
        action="reservation.requested",
        resource_type="scheduled_reservation",
        resource_id=str(item.reservation_id),
        outcome=AuditOutcome.SUCCESS,
        reason="test",
        correlation_id=uuid4(),
        source_module="scheduled",
    )


def test_recovery_is_restart_safe_bounded_and_state_driven() -> None:
    item = reservation(state=ReservationState.DRIVER_COMMITTED)
    checkpoint = ReservationCheckpoint(
        reservation_id=item.reservation_id, kind=CheckpointType.REVALIDATION, due_at=NOW
    )
    assert (
        recover_checkpoint(item, checkpoint, policy(), now=NOW).action
        is RecoveryAction.REVALIDATE
    )
    exhausted = checkpoint.model_copy(update={"attempt_count": 5})
    assert (
        recover_checkpoint(item, exhausted, policy(), now=NOW).action
        is RecoveryAction.OPERATIONAL_REVIEW
    )


def test_state_machine_rejects_invalid_transition() -> None:
    with pytest.raises(ReservationConflict):
        transition(reservation(), ReservationState.FULFILLED, now=NOW)


def test_models_reject_naive_time_and_same_places() -> None:
    with pytest.raises(ValidationError):
        reservation(requested_pickup_at=datetime(2026, 7, 20, 12))
    with pytest.raises(ValidationError):
        reservation(destination_place_id="place.addis.bole")
