from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from BACKEND.arrival_waiting.engine import (
    ArrivalWaitingConflict,
    evaluate_arrival,
    evaluate_evidence,
    evaluate_readiness,
    evaluate_waiting_continuity,
    resolve_waiting_policy,
    start_waiting,
)
from BACKEND.arrival_waiting.models import (
    ArrivalPolicy,
    ArrivalSignals,
    ArrivalState,
    ContinuitySignals,
    DepartureBehavior,
    LocationObservation,
    PickupContext,
    ReadinessClass,
    ReadinessPolicy,
    ReadinessSignals,
    ResponsibilityClass,
    RideOrigin,
    ServiceContext,
    WaitingPolicyContext,
    WaitingPolicyDefinition,
    WaitingState,
)

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def arrival_policy() -> ArrivalPolicy:
    return ArrivalPolicy(
        policy_id="arrival.default",
        version="v1",
        maximum_location_age_seconds=30,
        maximum_accuracy_meters=30,
        maximum_stationary_speed_cm_per_second=100,
        minimum_stationary_seconds=20,
        minimum_pickup_confidence_bps=8000,
        minimum_map_confidence_bps=7000,
        minimum_verification_confidence_bps=8000,
    )


def arrival_signals(**updates) -> ArrivalSignals:
    values = {
        "observation": LocationObservation(
            observed_at=NOW,
            sequence=10,
            latitude_e6=9_005_000,
            longitude_e6=38_763_000,
            accuracy_meters=8,
            speed_cm_per_second=0,
            heading_degrees=90,
        ),
        "approved_pickup_place_id": "place.addis.bole",
        "pickup_recommendation_id": uuid4(),
        "pickup_recommendation_version": "v1",
        "pickup_zone_id": "zone.bole.gate_1",
        "inside_pickup_zone": True,
        "pickup_confidence_bps": 9500,
        "map_confidence_bps": 9000,
        "seconds_stationary": 30,
        "approach_consistent": True,
        "heading_reliable": True,
        "accessible_pickup": True,
        "operationally_available": True,
    }
    values.update(updates)
    return ArrivalSignals(**values)


def context(**updates) -> WaitingPolicyContext:
    values = {
        "city_code": "addis_ababa",
        "ride_origin": RideOrigin.IMMEDIATE,
        "pickup_context": PickupContext.RESIDENTIAL,
        "service_context": ServiceContext.STANDARD,
    }
    values.update(updates)
    return WaitingPolicyContext(**values)


def policy(**updates) -> WaitingPolicyDefinition:
    values = {
        "version": "v1",
        "city_code": "addis_ababa",
        "effective_from": NOW - timedelta(days=1),
        "free_wait_seconds": 300,
        "ending_warning_seconds": 60,
        "departure_behavior": DepartureBehavior.PAUSE,
        "pause_on_insufficient_quality": True,
        "maximum_location_age_seconds": 30,
        "minimum_location_confidence_bps": 8000,
    }
    values.update(updates)
    return WaitingPolicyDefinition(**values)


def continuity(**updates) -> ContinuitySignals:
    values = {
        "inside_pickup_zone": True,
        "location_age_seconds": 2,
        "location_confidence_bps": 9500,
        "driver_available": True,
        "pickup_guidance_valid": True,
        "reasonable_notification": True,
    }
    values.update(updates)
    return ContinuitySignals(**values)


def verified_arrival():
    return evaluate_arrival(
        uuid4(), uuid4(), arrival_signals(), arrival_policy(), now=NOW
    )


def test_arrival_requires_multiple_signals_and_is_deterministic():
    ride_id, assignment_id = uuid4(), uuid4()
    first = evaluate_arrival(
        ride_id, assignment_id, arrival_signals(), arrival_policy(), now=NOW
    )
    second = evaluate_arrival(
        ride_id, assignment_id, arrival_signals(), arrival_policy(), now=NOW
    )
    assert first.state is ArrivalState.ARRIVAL_VERIFIED
    assert first.model_dump(exclude={"evaluation_id", "pickup_recommendation_id"}) == (
        second.model_dump(exclude={"evaluation_id", "pickup_recommendation_id"})
    )


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"inside_pickup_zone": False}, "arrival.outside_pickup_zone"),
        ({"seconds_stationary": 0}, "arrival.stationarity_insufficient"),
        ({"approach_consistent": False}, "arrival.approach_inconsistent"),
        ({"map_confidence_bps": 2000}, "arrival.map_confidence_low"),
    ],
)
def test_gps_proximity_alone_never_verifies_arrival(updates, reason):
    decision = evaluate_arrival(
        uuid4(), uuid4(), arrival_signals(**updates), arrival_policy(), now=NOW
    )
    assert decision.state is ArrivalState.ARRIVAL_UNVERIFIED
    assert reason in decision.reason_codes


def test_stale_and_drifted_location_prevent_false_arrival():
    observation = arrival_signals().observation.model_copy(
        update={"observed_at": NOW - timedelta(minutes=2), "accuracy_meters": 500}
    )
    decision = evaluate_arrival(
        uuid4(),
        uuid4(),
        arrival_signals(observation=observation),
        arrival_policy(),
        now=NOW,
    )
    assert set(decision.reason_codes) >= {
        "arrival.location_stale",
        "arrival.location_inaccurate",
    }


def test_airport_arrival_requires_terminal_zone_staging_and_access():
    decision = evaluate_arrival(
        uuid4(),
        uuid4(),
        arrival_signals(
            service_context=ServiceContext.AIRPORT_PREMIUM,
            airport_terminal_code=None,
            airport_zone_match=False,
            airport_context_fresh=False,
            airport_staging_constraint_satisfied=False,
            airport_access_permitted=False,
        ),
        arrival_policy(),
        now=NOW,
    )
    assert decision.state is ArrivalState.ARRIVAL_UNVERIFIED
    assert set(decision.reason_codes) >= {
        "arrival.airport_zone_mismatch",
        "arrival.airport_context_stale",
        "arrival.airport_staging_constraint",
        "arrival.airport_access_unavailable",
    }


def test_readiness_is_advisory_deterministic_and_does_not_claim_private_location():
    signals = ReadinessSignals(
        rider_location_age_seconds=5,
        rider_location_accuracy_meters=10,
        moving_toward_pickup=False,
        rider_walking_eta_seconds=240,
        driver_eta_seconds=60,
        venue_context_possible=True,
        pickup_confidence_bps=9000,
    )
    rules = ReadinessPolicy(
        policy_id="readiness.default",
        version="v1",
        maximum_location_age_seconds=30,
        maximum_accuracy_meters=50,
        minimum_confidence_bps=7000,
        notification_confidence_bps=8500,
        notification_cooldown_seconds=120,
        maximum_notifications_per_ride=2,
        lateness_margin_seconds=60,
    )
    decision = evaluate_readiness(uuid4(), signals, rules, now=NOW)
    assert decision.classification is ReadinessClass.UNLIKELY_ON_TIME
    assert decision.notification_recommended
    assert "not_verified" in " ".join(decision.reason_codes)
    assert "inside" not in decision.explanation_code
    suppressed = evaluate_readiness(
        decision.ride_id,
        signals,
        rules,
        now=NOW,
        prior_notification_at=NOW - timedelta(seconds=10),
        notification_count=1,
    )
    assert not suppressed.notification_recommended
    assert suppressed.notification_reason_code == "notification.suppressed_cooldown"


def test_readiness_stale_location_is_insufficient():
    result = evaluate_readiness(
        uuid4(),
        ReadinessSignals(
            rider_location_age_seconds=500,
            rider_location_accuracy_meters=10,
            rider_walking_eta_seconds=60,
            driver_eta_seconds=60,
            pickup_confidence_bps=9000,
        ),
        ReadinessPolicy(
            policy_id="readiness.default",
            version="v1",
            maximum_location_age_seconds=30,
            maximum_accuracy_meters=50,
            minimum_confidence_bps=7000,
            notification_confidence_bps=8000,
            notification_cooldown_seconds=60,
            maximum_notifications_per_ride=2,
            lateness_margin_seconds=30,
        ),
        now=NOW,
    )
    assert result.classification is ReadinessClass.INSUFFICIENT_DATA
    assert not result.notification_recommended


@pytest.mark.parametrize(
    ("signal_updates", "expected"),
    [
        ({"within_pickup_zone": True}, ReadinessClass.READY),
        ({"moving_toward_pickup": True}, ReadinessClass.MOVING_TO_PICKUP),
        ({"rider_walking_eta_seconds": 30}, ReadinessClass.LIKELY_ON_TIME),
        ({"rider_walking_eta_seconds": 90}, ReadinessClass.MAY_BE_LATE),
    ],
)
def test_readiness_classification_branches(signal_updates, expected):
    values = {
        "rider_location_age_seconds": 1,
        "rider_location_accuracy_meters": 5,
        "moving_toward_pickup": False,
        "rider_walking_eta_seconds": 180,
        "driver_eta_seconds": 60,
        "pickup_confidence_bps": 9500,
    }
    values.update(signal_updates)
    result = evaluate_readiness(
        uuid4(),
        ReadinessSignals(**values),
        ReadinessPolicy(
            policy_id="readiness.default",
            version="v1",
            maximum_location_age_seconds=30,
            maximum_accuracy_meters=50,
            minimum_confidence_bps=7000,
            notification_confidence_bps=8000,
            notification_cooldown_seconds=60,
            maximum_notifications_per_ride=2,
            lateness_margin_seconds=60,
        ),
        now=NOW,
    )
    assert result.classification is expected


def test_policy_precedence_snapshot_and_accessibility():
    base = policy(priority=1)
    accessible = policy(
        priority=2,
        accessibility_accommodation=True,
        free_wait_seconds=600,
        ending_warning_seconds=120,
    )
    snapshot = resolve_waiting_policy(
        uuid4(),
        context(accessibility_accommodation=True),
        (base, accessible),
        now=NOW,
    )
    assert snapshot.source_policy_id == accessible.policy_id
    assert snapshot.free_wait_seconds == 600
    assert "waiting_policy.context.accessibility_accommodation" in (
        snapshot.matched_dimensions
    )


def test_policy_missing_or_ambiguous_fails_closed():
    with pytest.raises(ArrivalWaitingConflict, match="waiting_policy_unavailable"):
        resolve_waiting_policy(uuid4(), context(), (), now=NOW)
    first, second = policy(priority=1), policy(priority=1)
    with pytest.raises(ArrivalWaitingConflict, match="waiting_policy_ambiguous"):
        resolve_waiting_policy(uuid4(), context(), (first, second), now=NOW)


def test_airport_standard_and_premium_are_separate():
    standard = policy(
        pickup_context=PickupContext.AIRPORT,
        service_context=ServiceContext.AIRPORT_STANDARD,
        free_wait_seconds=300,
    )
    premium = policy(
        pickup_context=PickupContext.AIRPORT,
        service_context=ServiceContext.AIRPORT_PREMIUM,
        free_wait_seconds=900,
    )
    standard_snapshot = resolve_waiting_policy(
        uuid4(),
        context(
            pickup_context=PickupContext.AIRPORT,
            service_context=ServiceContext.AIRPORT_STANDARD,
        ),
        (standard, premium),
        now=NOW,
    )
    premium_snapshot = resolve_waiting_policy(
        uuid4(),
        context(
            pickup_context=PickupContext.AIRPORT,
            service_context=ServiceContext.AIRPORT_PREMIUM,
        ),
        (standard, premium),
        now=NOW,
    )
    assert standard_snapshot.source_policy_id == standard.policy_id
    assert premium_snapshot.source_policy_id == premium.policy_id


def test_waiting_requires_verified_arrival_and_snapshot_is_immutable():
    arrival = verified_arrival()
    snapshot = resolve_waiting_policy(arrival.ride_id, context(), (policy(),), now=NOW)
    session = start_waiting(
        arrival.ride_id, arrival.assignment_id, arrival, snapshot, now=NOW
    )
    assert session.state is WaitingState.FREE_WAIT_ACTIVE
    assert session.free_wait_deadline == NOW + timedelta(seconds=300)
    unverified = arrival.model_copy(update={"state": ArrivalState.ARRIVAL_UNVERIFIED})
    with pytest.raises(ArrivalWaitingConflict, match="arrival_not_verified"):
        start_waiting(
            arrival.ride_id, arrival.assignment_id, unverified, snapshot, now=NOW
        )


def test_driver_leaving_pauses_and_policy_can_invalidate():
    arrival = verified_arrival()
    pause_snapshot = resolve_waiting_policy(
        arrival.ride_id, context(), (policy(),), now=NOW
    )
    session = start_waiting(
        arrival.ride_id, arrival.assignment_id, arrival, pause_snapshot, now=NOW
    )
    paused = evaluate_waiting_continuity(
        session,
        pause_snapshot,
        continuity(inside_pickup_zone=False),
        observation_sequence=11,
        now=NOW + timedelta(seconds=10),
    )
    assert paused.state is WaitingState.WAIT_PAUSED
    invalidate_snapshot = resolve_waiting_policy(
        arrival.ride_id,
        context(),
        (policy(departure_behavior=DepartureBehavior.INVALIDATE),),
        now=NOW,
    )
    invalidated = evaluate_waiting_continuity(
        session,
        invalidate_snapshot,
        continuity(inside_pickup_zone=False),
        observation_sequence=11,
        now=NOW + timedelta(seconds=10),
    )
    assert invalidated.state is WaitingState.WAIT_INVALIDATED


def test_waiting_quality_pause_ending_and_stale_sequence():
    arrival = verified_arrival()
    snapshot = resolve_waiting_policy(arrival.ride_id, context(), (policy(),), now=NOW)
    session = start_waiting(
        arrival.ride_id, arrival.assignment_id, arrival, snapshot, now=NOW
    )
    paused = evaluate_waiting_continuity(
        session,
        snapshot,
        continuity(location_age_seconds=100),
        observation_sequence=11,
        now=NOW + timedelta(seconds=10),
    )
    assert paused.state is WaitingState.WAIT_PAUSED
    assert paused.paused_at == NOW + timedelta(seconds=10)
    resumed = evaluate_waiting_continuity(
        paused,
        snapshot,
        continuity(),
        observation_sequence=12,
        now=NOW + timedelta(seconds=40),
    )
    assert resumed.state is WaitingState.FREE_WAIT_ACTIVE
    assert resumed.total_paused_seconds == 30
    assert resumed.free_wait_deadline == session.free_wait_deadline + timedelta(
        seconds=30
    )
    ending = evaluate_waiting_continuity(
        session,
        snapshot,
        continuity(),
        observation_sequence=11,
        now=NOW + timedelta(seconds=250),
    )
    assert ending.state is WaitingState.FREE_WAIT_ENDING


def test_evidence_ready_and_every_material_suppression():
    arrival = verified_arrival()
    snapshot = resolve_waiting_policy(arrival.ride_id, context(), (policy(),), now=NOW)
    session = start_waiting(
        arrival.ride_id, arrival.assignment_id, arrival, snapshot, now=NOW
    )
    later = NOW + timedelta(seconds=301)
    ready = evaluate_evidence(session, snapshot, continuity(), now=later)
    assert ready.ready
    assert ready.responsibility is ResponsibilityClass.RIDER
    suppressed = evaluate_evidence(
        session,
        snapshot,
        continuity(
            reasonable_notification=False,
            platform_failure=True,
            map_or_eta_failure=True,
            external_disruption=True,
            airport_zone_confusion=True,
            road_closure=True,
            emergency=True,
            weak_network_uncertainty=True,
        ),
        now=later,
    )
    assert not suppressed.ready
    assert suppressed.responsibility is ResponsibilityClass.EXTERNAL
    assert set(suppressed.suppression_reason_codes) >= {
        "suppression.notification_failure",
        "suppression.platform_failure",
        "suppression.map_or_eta_failure",
        "suppression.airport_zone_confusion",
        "suppression.road_closure",
        "suppression.emergency",
        "suppression.weak_network_uncertainty",
    }


def test_stale_continuity_observation_is_rejected():
    arrival = verified_arrival()
    snapshot = resolve_waiting_policy(arrival.ride_id, context(), (policy(),), now=NOW)
    session = start_waiting(
        arrival.ride_id, arrival.assignment_id, arrival, snapshot, now=NOW
    )
    with pytest.raises(ArrivalWaitingConflict, match="stale_location_observation"):
        evaluate_waiting_continuity(
            session,
            snapshot,
            continuity(),
            observation_sequence=session.last_observation_sequence,
            now=NOW,
        )
