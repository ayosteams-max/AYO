from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.active_ride.engine import (
    ActiveRideConflict,
    evaluate_confidence,
    transition,
    translate_legacy_status,
)
from BACKEND.active_ride.models import (
    ActiveRide,
    ActiveRideState,
    ConfidenceLevel,
    ConfidencePolicy,
    ConfidenceSignals,
    PickupConfidence,
)
from BACKEND.active_ride.pickup import PickupCandidate, recommend_pickup
from BACKEND.domain.rides import RideStatus

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def ride(state: ActiveRideState = ActiveRideState.ASSIGNED) -> ActiveRide:
    return ActiveRide(
        rider_id=uuid4(),
        driver_id=uuid4(),
        assignment_id=uuid4(),
        state=state,
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="ayo.go",
        created_at=NOW,
        updated_at=NOW,
        last_sequence=1,
    )


def test_canonical_lifecycle_and_unsupported_transition():
    current = ride()
    path = [
        ActiveRideState.DRIVER_EN_ROUTE,
        ActiveRideState.DRIVER_ARRIVED,
        ActiveRideState.PICKUP_VERIFICATION_PENDING,
        ActiveRideState.PICKUP_VERIFIED,
        ActiveRideState.IN_PROGRESS,
        ActiveRideState.DESTINATION_APPROACHING,
        ActiveRideState.COMPLETION_PENDING,
        ActiveRideState.COMPLETED,
    ]
    for state in path:
        current = transition(current, state, now=NOW)
    assert current.state is ActiveRideState.COMPLETED
    assert current.version == 1 + len(path)
    with pytest.raises(ActiveRideConflict, match="unsupported_transition"):
        transition(current, ActiveRideState.IN_PROGRESS, now=NOW)


def test_legacy_translation_is_explicit_and_ambiguous_state_rejected():
    assert (
        translate_legacy_status(RideStatus.DRIVER_ACCEPTED) is ActiveRideState.ASSIGNED
    )
    assert (
        translate_legacy_status(RideStatus.TRIP_STARTED) is ActiveRideState.IN_PROGRESS
    )
    with pytest.raises(ActiveRideConflict, match="ambiguous_legacy_status"):
        translate_legacy_status(RideStatus.DRIVER_DECLINED)


def test_confidence_missing_data_is_insufficient_and_non_blocking():
    decision = evaluate_confidence(
        uuid4(), ConfidenceSignals(), ConfidencePolicy(), now=NOW
    )
    assert decision.health_level is ConfidenceLevel.INSUFFICIENT_DATA
    assert decision.recommended_actions == ("request_location_observation",)


def test_confidence_replay_is_deterministic_and_external_delay_is_protective():
    ride_id = uuid4()
    signals = ConfidenceSignals(
        driver_location_age_seconds=5,
        rider_location_age_seconds=6,
        driver_moving_away=True,
        verified_external_delay=True,
        anomaly_duration_seconds=180,
    )
    first = evaluate_confidence(ride_id, signals, ConfidencePolicy(), now=NOW)
    second = evaluate_confidence(ride_id, signals, ConfidencePolicy(), now=NOW)
    assert first.model_dump(exclude={"confidence_decision_id"}) == second.model_dump(
        exclude={"confidence_decision_id"}
    )
    assert first.health_level is ConfidenceLevel.AT_RISK
    assert "verified_external_delay" in first.reason_codes
    assert not any("punish" in action for action in first.recommended_actions)


def test_confidence_hysteresis_and_cooldown_suppress_false_positive_alerts():
    ride_id = uuid4()
    policy = ConfidencePolicy(hysteresis_seconds=120, alert_cooldown_seconds=600)
    early = evaluate_confidence(
        ride_id,
        ConfidenceSignals(
            driver_location_age_seconds=5,
            rider_location_age_seconds=5,
            driver_moving_away=True,
            anomaly_duration_seconds=30,
        ),
        policy,
        now=NOW,
    )
    assert early.health_level is ConfidenceLevel.WATCH
    assert "stability_margin_not_met" in early.reason_codes
    repeated = evaluate_confidence(
        ride_id,
        ConfidenceSignals(
            driver_location_age_seconds=5,
            rider_location_age_seconds=5,
            pickup_eta_increase_seconds=200,
        ),
        policy,
        now=NOW,
        previous=early,
    )
    assert repeated.recommended_actions == ()
    assert "alert_cooldown_active" in repeated.reason_codes


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (
            PickupCandidate(
                place_id="place.airport.zone_a",
                approach_guidance="Use Zone A",
                legal_access_verified=True,
                accessibility_supported=True,
            ),
            PickupConfidence.VERIFIED,
        ),
        (
            PickupCandidate(
                place_id="place.divided.road",
                fallback_place_id="place.safe.fallback",
                approach_guidance="Use the safe side",
                divided_road_conflict=True,
            ),
            PickupConfidence.LOW,
        ),
        (
            PickupCandidate(
                place_id="place.cached.zone",
                approach_guidance="Cached entrance",
                provider_available=False,
                cached=True,
            ),
            PickupConfidence.INSUFFICIENT_DATA,
        ),
    ],
)
def test_dynamic_pickup_scenarios(candidate, expected):
    result = recommend_pickup(uuid4(), candidate, now=NOW)
    assert result.confidence is expected


def test_material_pickup_change_requires_confirmation_state():
    result = recommend_pickup(
        uuid4(),
        PickupCandidate(
            place_id="place.airport.zone_b",
            fallback_place_id="place.airport.zone_c",
            approach_guidance="Terminal 2 Zone B",
            material_change=True,
        ),
        now=NOW,
    )
    assert result.material_change
    assert result.change_status == "proposed"
