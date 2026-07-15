from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.active_ride.application import (
    ActiveRideApplication,
    CommandEnvelope,
    PickupChangeCommand,
    PickupVerifyCommand,
    ProgressCommand,
)
from BACKEND.active_ride.engine import ActiveRideConflict
from BACKEND.active_ride.models import (
    ActiveRide,
    ActiveRideState,
    ConfidenceSignals,
)
from BACKEND.active_ride.pickup import PickupCandidate, recommend_pickup
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import IdentityType

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def subject(identity_id, identity_type):
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=identity_type,
        actor_type=ActorType.RIDER
        if identity_type is IdentityType.RIDER
        else ActorType.DRIVER,
    )


def test_postgres_two_device_lifecycle_converges_and_pin_is_single_use(
    postgres_composition,
):
    rider_id, driver_id, ride_id, assignment_id = uuid4(), uuid4(), uuid4(), uuid4()
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
                service_type="ayo.go",
                created_at=NOW,
                updated_at=NOW,
                last_sequence=1,
            )
        )
        pickup = recommend_pickup(
            ride_id,
            PickupCandidate(
                place_id="place.addis.bole",
                fallback_place_id="place.addis.bole_gate",
                approach_guidance="Approach from Airport Road",
                legal_access_verified=True,
                accessibility_supported=True,
            ),
            now=NOW,
        )
        unit.active_rides.save_pickup_recommendation(pickup)

    app = ActiveRideApplication(postgres_composition.unit_of_work, pin_secret=b"x" * 32)
    rider = subject(rider_id, IdentityType.RIDER)
    driver = subject(driver_id, IdentityType.DRIVER)
    version = 1

    def driver_command(name, target, *, progress=None):
        nonlocal version
        command = (
            ProgressCommand(
                command_id=uuid4(),
                expected_version=version,
                progress_basis_points=progress,
            )
            if progress is not None
            else CommandEnvelope(command_id=uuid4(), expected_version=version)
        )
        result = app.command(
            driver,
            ride_id,
            command,
            command_type=name,
            target=target,
            driver_only=True,
            now=NOW,
        )
        version = result["aggregate_version"]

    driver_command("driver_en_route", ActiveRideState.DRIVER_EN_ROUTE)
    driver_command("driver_arrived", ActiveRideState.DRIVER_ARRIVED)
    challenge = app.issue_verification(
        rider,
        ride_id,
        CommandEnvelope(command_id=uuid4(), expected_version=version),
        now=NOW,
    )
    version += 1
    verified = app.verify_pickup(
        driver,
        ride_id,
        PickupVerifyCommand(
            command_id=uuid4(), expected_version=version, code=challenge["pickup_code"]
        ),
        now=NOW,
    )
    version = verified["aggregate_version"]
    with pytest.raises(ActiveRideConflict, match="verification_not_available"):
        app.verify_pickup(
            driver,
            ride_id,
            PickupVerifyCommand(
                command_id=uuid4(),
                expected_version=version,
                code=challenge["pickup_code"],
            ),
            now=NOW,
        )

    driver_command("trip_started", ActiveRideState.IN_PROGRESS)
    driver_command("trip_progress_updated", ActiveRideState.IN_PROGRESS, progress=5000)
    driver_command("destination_approaching", ActiveRideState.DESTINATION_APPROACHING)
    driver_command("completion_requested", ActiveRideState.COMPLETION_PENDING)
    driver_command("trip_completed", ActiveRideState.COMPLETED)

    rider_snapshot = app.snapshot(rider, ride_id)
    driver_snapshot = app.snapshot(driver, ride_id)
    assert rider_snapshot["state"] == driver_snapshot["state"] == "completed"
    assert rider_snapshot["aggregate_version"] == driver_snapshot["aggregate_version"]
    events = app.events(rider, ride_id, after=0, limit=100)
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert "driver_reference" in rider_snapshot["driver"]
    assert "rider_reference" in driver_snapshot["rider"]
    assert "trust_score" not in str(rider_snapshot)


def test_idempotent_command_and_stale_command_rejection(postgres_composition):
    rider_id, driver_id, ride_id = uuid4(), uuid4(), uuid4()
    with postgres_composition.unit_of_work() as unit:
        unit.active_rides.create_from_assignment(
            ActiveRide(
                ride_id=ride_id,
                rider_id=rider_id,
                driver_id=driver_id,
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
    app = ActiveRideApplication(postgres_composition.unit_of_work, pin_secret=b"x" * 32)
    driver = subject(driver_id, IdentityType.DRIVER)
    command = CommandEnvelope(command_id=uuid4(), expected_version=1)
    first = app.command(
        driver,
        ride_id,
        command,
        command_type="driver_en_route",
        target=ActiveRideState.DRIVER_EN_ROUTE,
        driver_only=True,
        now=NOW,
    )
    duplicate = app.command(
        driver,
        ride_id,
        command,
        command_type="driver_en_route",
        target=ActiveRideState.DRIVER_EN_ROUTE,
        driver_only=True,
        now=NOW,
    )
    assert first["aggregate_version"] == duplicate["aggregate_version"] == 2
    assert duplicate["command_created"] is False
    with pytest.raises(ActiveRideConflict, match="stale_command"):
        app.command(
            driver,
            ride_id,
            CommandEnvelope(command_id=uuid4(), expected_version=1),
            command_type="driver_arrived",
            target=ActiveRideState.DRIVER_ARRIVED,
            driver_only=True,
            now=NOW,
        )


def test_confidence_and_pickup_persist_without_controlling_ride(postgres_composition):
    rider_id, ride_id = uuid4(), uuid4()
    with postgres_composition.unit_of_work() as unit:
        unit.active_rides.create_from_assignment(
            ActiveRide(
                ride_id=ride_id,
                rider_id=rider_id,
                driver_id=uuid4(),
                assignment_id=uuid4(),
                state=ActiveRideState.ASSIGNED,
                pickup_place_id="place.airport.zone_a",
                destination_place_id="place.addis.center",
                service_type="airport.standard",
                created_at=NOW,
                updated_at=NOW,
                last_sequence=1,
            )
        )
    app = ActiveRideApplication(postgres_composition.unit_of_work, pin_secret=b"x" * 32)
    rider = subject(rider_id, IdentityType.RIDER)
    decision = app.evaluate_confidence(
        rider,
        ride_id,
        ConfidenceSignals(
            driver_location_age_seconds=5,
            rider_location_age_seconds=5,
            driver_moving_away=True,
            anomaly_duration_seconds=180,
        ),
        now=NOW,
    )
    assert decision.health_level.value == "at_risk"
    assert app.snapshot(rider, ride_id)["state"] == "assigned"
    assert (
        app.confidence(rider, ride_id).confidence_decision_id
        == decision.confidence_decision_id
    )
    with postgres_composition.unit_of_work() as unit:
        item = recommend_pickup(
            ride_id,
            PickupCandidate(
                place_id="place.airport.zone_b",
                fallback_place_id="place.airport.zone_c",
                approach_guidance="Zone B closed; use Zone C",
                temporary_closure=True,
                material_change=True,
            ),
            now=NOW,
        )
        unit.active_rides.save_pickup_recommendation(item)
    proposed = app.pickup(rider, ride_id)
    assert proposed.change_status == "proposed"
    declined = app.pickup_change(
        rider,
        ride_id,
        PickupChangeCommand(
            recommendation_id=proposed.recommendation_id, confirmed=False
        ),
    )
    assert declined.change_status == "declined"
