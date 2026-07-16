from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from BACKEND.active_ride.models import ActiveRide, ActiveRideState
from BACKEND.arrival_waiting.application import (
    ArrivalCommand,
    ArrivalWaitingApplication,
    ContinuityCommand,
    EvidenceCommand,
    StartWaitingCommand,
)
from BACKEND.arrival_waiting.models import (
    ArrivalPolicy,
    ArrivalSignals,
    ContinuitySignals,
    DepartureBehavior,
    LocationObservation,
    PickupContext,
    ReadinessPolicy,
    RideOrigin,
    ServiceContext,
    WaitingPolicyContext,
    WaitingPolicyDefinition,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.tables import dispatch_outbox, waiting_session_events

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def driver_subject(driver_id):
    return AuthorizationSubject(
        identity_id=driver_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )


def application(composition):
    return ArrivalWaitingApplication(
        composition.unit_of_work,
        arrival_policy=ArrivalPolicy(
            policy_id="arrival.default",
            version="v1",
            maximum_location_age_seconds=30,
            maximum_accuracy_meters=30,
            maximum_stationary_speed_cm_per_second=100,
            minimum_stationary_seconds=20,
            minimum_pickup_confidence_bps=8000,
            minimum_map_confidence_bps=8000,
            minimum_verification_confidence_bps=8000,
        ),
        readiness_policy=ReadinessPolicy(
            policy_id="readiness.default",
            version="v1",
            maximum_location_age_seconds=30,
            maximum_accuracy_meters=50,
            minimum_confidence_bps=7000,
            notification_confidence_bps=8500,
            notification_cooldown_seconds=120,
            maximum_notifications_per_ride=2,
            lateness_margin_seconds=60,
        ),
        waiting_policies=(
            WaitingPolicyDefinition(
                version="v1",
                city_code="addis_ababa",
                ride_origin=RideOrigin.IMMEDIATE,
                pickup_context=PickupContext.RESIDENTIAL,
                service_context=ServiceContext.STANDARD,
                effective_from=NOW - timedelta(days=1),
                free_wait_seconds=300,
                ending_warning_seconds=60,
                departure_behavior=DepartureBehavior.PAUSE,
                pause_on_insufficient_quality=True,
                maximum_location_age_seconds=30,
                minimum_location_confidence_bps=8000,
            ),
        ),
    )


def continuity(**updates):
    values = {
        "inside_pickup_zone": True,
        "location_age_seconds": 1,
        "location_confidence_bps": 9500,
        "driver_available": True,
        "pickup_guidance_valid": True,
        "reasonable_notification": True,
    }
    values.update(updates)
    return ContinuitySignals(**values)


def test_postgres_arrival_waiting_evidence_and_outbox_are_atomic(
    postgres_composition,
):
    rider_id, driver_id, ride_id, assignment_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with postgres_composition.unit_of_work() as unit:
        unit.active_rides.create_from_assignment(
            ActiveRide(
                ride_id=ride_id,
                rider_id=rider_id,
                driver_id=driver_id,
                assignment_id=assignment_id,
                state=ActiveRideState.ASSIGNED,
                pickup_place_id="place.addis.bole",
                destination_place_id="place.addis.saris",
                service_type="standard",
                created_at=NOW,
                updated_at=NOW,
                last_sequence=1,
            )
        )
        unit.active_rides.command_transition(
            ride_id=ride_id,
            actor_id=driver_id,
            command_id=uuid4(),
            command_type="driver_en_route",
            request_payload={},
            expected_version=1,
            target=ActiveRideState.DRIVER_EN_ROUTE,
            now=NOW,
        )
        unit.active_rides.command_transition(
            ride_id=ride_id,
            actor_id=driver_id,
            command_id=uuid4(),
            command_type="driver_arrived",
            request_payload={},
            expected_version=2,
            target=ActiveRideState.DRIVER_ARRIVED,
            now=NOW,
        )
    app = application(postgres_composition)
    driver = driver_subject(driver_id)
    arrival_command = ArrivalCommand(
        command_id=uuid4(),
        expected_ride_version=3,
        signals=ArrivalSignals(
            observation=LocationObservation(
                observed_at=NOW,
                sequence=5,
                latitude_e6=9_005_000,
                longitude_e6=38_763_000,
                accuracy_meters=5,
                speed_cm_per_second=0,
                heading_degrees=90,
            ),
            approved_pickup_place_id="place.addis.bole",
            pickup_recommendation_id=uuid4(),
            pickup_recommendation_version="v1",
            pickup_zone_id="zone.bole.gate_1",
            inside_pickup_zone=True,
            pickup_confidence_bps=9500,
            map_confidence_bps=9000,
            seconds_stationary=30,
            approach_consistent=True,
            heading_reliable=True,
            accessible_pickup=True,
            operationally_available=True,
        ),
    )
    first = app.submit_arrival(driver, ride_id, arrival_command, now=NOW)
    duplicate = app.submit_arrival(driver, ride_id, arrival_command, now=NOW)
    assert first == duplicate
    assert first["state"] == "arrival_verified"
    started = app.start(
        driver,
        ride_id,
        StartWaitingCommand(
            command_id=uuid4(),
            expected_ride_version=3,
            context=WaitingPolicyContext(
                city_code="addis_ababa",
                ride_origin=RideOrigin.IMMEDIATE,
                pickup_context=PickupContext.RESIDENTIAL,
                service_context=ServiceContext.STANDARD,
            ),
        ),
        now=NOW,
    )
    paused = app.continuity(
        driver,
        ride_id,
        ContinuityCommand(
            command_id=uuid4(),
            expected_session_version=started["version"],
            observation_sequence=6,
            signals=continuity(inside_pickup_zone=False),
        ),
        now=NOW + timedelta(seconds=30),
    )
    assert paused["state"] == "wait_paused"
    suppressed = app.evaluate_no_show(
        driver,
        ride_id,
        EvidenceCommand(
            command_id=uuid4(),
            expected_session_version=paused["version"],
            signals=continuity(inside_pickup_zone=False),
        ),
        now=NOW + timedelta(seconds=301),
    )
    assert not suppressed["ready"]
    assert suppressed["responsibility"] == "driver_responsibility"
    with postgres_composition.unit_of_work() as unit:
        event_count = unit.connection.execute(
            select(waiting_session_events).where(
                waiting_session_events.c.ride_id == ride_id
            )
        ).all()
        outbox_types = set(
            unit.connection.execute(
                select(dispatch_outbox.c.event_type).where(
                    dispatch_outbox.c.aggregate_id == ride_id
                )
            ).scalars()
        )
    assert len(event_count) == 2
    assert {
        "arrival.driver_arrival_verified",
        "arrival.free_wait_started",
        "arrival.waiting_paused",
        "arrival.consequence_suppressed",
    } <= outbox_types
