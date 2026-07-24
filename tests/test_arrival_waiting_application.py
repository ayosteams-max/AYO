from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from BACKEND.active_ride.models import ActiveRide, ActiveRideState
from BACKEND.arrival_waiting.application import (
    ArrivalCommand,
    ArrivalWaitingApplication,
    ContinuityCommand,
    EvidenceCommand,
    ReadinessCommand,
    RiderPresentCommand,
    StartWaitingCommand,
)
from BACKEND.arrival_waiting.engine import ArrivalWaitingConflict
from BACKEND.arrival_waiting.models import (
    ArrivalPolicy,
    ArrivalSignals,
    ContinuitySignals,
    DepartureBehavior,
    ExactStoppingPosition,
    LandmarkReference,
    LocationObservation,
    NamedPickupPoint,
    PickupContext,
    PickupPointKind,
    PickupReferencePhotoReference,
    ReadinessPolicy,
    ReadinessSignals,
    RideOrigin,
    ServiceContext,
    WaitingPolicyContext,
    WaitingPolicyDefinition,
    WalkingGuidance,
    WalkingGuidanceRequest,
)
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.main import ArrivalWaitingActivation, create_app
from BACKEND.observability import NullMetricsSink
from BACKEND.rate_limit.models import RateLimitDecision

NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


class ActiveRepo:
    def __init__(self, ride):
        self.ride = ride

    def get(self, ride_id, *, lock=False):
        del lock
        return self.ride if self.ride.ride_id == ride_id else None


class ArrivalRepo:
    def __init__(self):
        self.arrival = None
        self.readiness = None
        self.snapshot = None
        self.session = None
        self.evidence = None
        self.commands = {}
        self.notifications = []

    def latest_arrival(self, ride_id):
        return (
            self.arrival if self.arrival and self.arrival.ride_id == ride_id else None
        )

    def save_arrival(self, item):
        self.arrival = item

    def latest_readiness(self, ride_id):
        return (
            self.readiness
            if self.readiness and self.readiness.ride_id == ride_id
            else None
        )

    def save_readiness(self, item):
        self.readiness = item

    def save_snapshot(self, item):
        self.snapshot = item

    def get_snapshot(self, snapshot_id):
        return (
            self.snapshot
            if self.snapshot and self.snapshot.snapshot_id == snapshot_id
            else None
        )

    def latest_session(self, ride_id, *, lock=False):
        del lock
        return (
            self.session if self.session and self.session.ride_id == ride_id else None
        )

    def create_session(self, item):
        self.session = item

    def update_session(self, item, *, expected_version):
        if self.session.version != expected_version:
            raise ArrivalWaitingConflict("stale_waiting_session")
        self.session = item

    def latest_evidence(self, ride_id):
        return (
            self.evidence
            if self.evidence and self.evidence.ride_id == ride_id
            else None
        )

    def save_evidence(self, item):
        self.evidence = item

    def record_notification(self, **values):
        self.notifications.append(values)

    def idempotent_response(
        self,
        *,
        actor_id,
        command_id,
        ride_id,
        command_type,
        request_payload,
    ):
        key = (actor_id, command_id)
        existing = self.commands.get(key)
        if existing is None:
            return None
        if existing[:3] != (ride_id, command_type, request_payload):
            raise ArrivalWaitingConflict("idempotency_conflict")
        return existing[3]

    def save_idempotent_response(
        self,
        *,
        actor_id,
        command_id,
        ride_id,
        command_type,
        request_payload,
        response_payload,
        now,
    ):
        del now
        self.commands[(actor_id, command_id)] = (
            ride_id,
            command_type,
            request_payload,
            response_payload,
        )


class Uow:
    def __init__(self, active, arrival):
        self.active_rides = active
        self.arrival_waiting = arrival

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class Landmarks:
    def __init__(self, item):
        self.item = item

    def get(self, landmark_id, *, now):
        del now
        return self.item if self.item.landmark_id == landmark_id else None


class WalkingRoutes:
    def __init__(self, item):
        self.item = item

    def route(self, request, *, now):
        del request, now
        return self.item


def subject(identity_id, kind):
    actor = {
        IdentityType.DRIVER: ActorType.DRIVER,
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.STAFF: ActorType.STAFF,
        IdentityType.ADMINISTRATOR: ActorType.ADMINISTRATOR,
    }[kind]
    return AuthorizationSubject(
        identity_id=identity_id,
        identity_type=kind,
        actor_type=actor,
    )


def fixture_app():
    rider_id, driver_id, ride_id, assignment_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    ride = ActiveRide(
        ride_id=ride_id,
        rider_id=rider_id,
        driver_id=driver_id,
        assignment_id=assignment_id,
        state=ActiveRideState.DRIVER_ARRIVED,
        pickup_place_id="place.addis.bole",
        destination_place_id="place.addis.saris",
        service_type="standard",
        created_at=NOW,
        updated_at=NOW,
        version=3,
        last_sequence=3,
    )
    repo = ArrivalRepo()
    unit = Uow(ActiveRepo(ride), repo)
    stop = ExactStoppingPosition(
        latitude_e6=8_980_000,
        longitude_e6=38_799_000,
        heading_degrees=90,
        curb_side_code="curb.airport_side",
        position_confidence_bps=9500,
    )
    photo = PickupReferencePhotoReference(
        reference_id=uuid4(),
        version="v1",
        verification_code="operations.verified",
        provenance_code="airport.authority",
        alt_text_en="Blue Main Gate sign",
        alt_text_am="የዋናው በር ምልክት",
        verified_at=NOW,
        # Keep this route-activation fixture valid independently of wall-clock date.
        # Expiry behavior is covered separately with explicitly expired records.
        expires_at=NOW + timedelta(days=3650),
    )
    point = NamedPickupPoint(
        pickup_point_id=uuid4(),
        kind=PickupPointKind.MAIN_GATE,
        name_en="Main Gate Taxi Bay",
        name_am="ዋና በር ታክሲ ማቆሚያ",
        exact_stopping_position=stop,
        walking_instruction_en="Walk to the signed taxi bay at the Main Gate.",
        walking_instruction_am="ወደ ዋናው በር የታክሲ ማቆሚያ ይሂዱ።",
        reference_photo=photo,
    )
    landmark = LandmarkReference(
        landmark_id=uuid4(),
        canonical_name_en="Bole Airport",
        canonical_name_am="ቦሌ አየር ማረፊያ",
        entrance_or_gate="Gate 1",
        terminal_code="T2",
        side_of_road_guidance="Airport side",
        provenance_code="operations.verified",
        confidence_bps=9500,
        observed_at=NOW,
        expires_at=NOW + timedelta(days=3650),
        named_pickup_points=(point,),
    )
    walking = WalkingGuidance(
        pickup_point_id=point.pickup_point_id,
        origin_observation_sequence=7,
        destination=stop,
        distance_meters=180,
        duration_seconds=140,
        instruction_en="Walk east to the Main Gate taxi bay.",
        instruction_am="ወደ ምስራቅ ዋናው በር ይሂዱ።",
        confidence_bps=9000,
        route_version="route.v1",
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
    )
    app = ArrivalWaitingApplication(
        lambda: unit,
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
        landmarks=Landmarks(landmark),
        walking_guidance=WalkingRoutes(walking),
    )
    return app, repo, ride, landmark


def arrival_command(ride):
    return ArrivalCommand(
        command_id=uuid4(),
        expected_ride_version=ride.version,
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
            approved_pickup_place_id=ride.pickup_place_id,
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


def signals(**updates):
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


def test_complete_application_flow_and_idempotency():
    app, repo, ride, _ = fixture_app()
    driver = subject(ride.driver_id, IdentityType.DRIVER)
    rider = subject(ride.rider_id, IdentityType.RIDER)
    command = arrival_command(ride)
    arrival = app.submit_arrival(driver, ride.ride_id, command, now=NOW)
    assert arrival["state"] == "arrival_verified"
    assert app.submit_arrival(driver, ride.ride_id, command, now=NOW) == arrival
    readiness = app.evaluate_rider_readiness(
        rider,
        ride.ride_id,
        ReadinessCommand(
            command_id=uuid4(),
            signals=ReadinessSignals(
                rider_location_age_seconds=1,
                rider_location_accuracy_meters=5,
                moving_toward_pickup=False,
                rider_walking_eta_seconds=180,
                driver_eta_seconds=30,
                pickup_confidence_bps=9500,
            ),
        ),
        now=NOW,
    )
    assert readiness["notification_recommended"]
    started = app.start(
        driver,
        ride.ride_id,
        StartWaitingCommand(
            command_id=uuid4(),
            expected_ride_version=ride.version,
            context=WaitingPolicyContext(
                city_code="addis_ababa",
                ride_origin=RideOrigin.IMMEDIATE,
                pickup_context=PickupContext.RESIDENTIAL,
                service_context=ServiceContext.STANDARD,
            ),
        ),
        now=NOW,
    )
    assert started["state"] == "free_wait_active"
    assert app.waiting(rider, ride.ride_id, now=NOW)["countdown_seconds"] == 300
    app.rider_present(
        rider,
        ride.ride_id,
        RiderPresentCommand(
            command_id=uuid4(), expected_session_version=started["version"]
        ),
        now=NOW,
    )
    paused = app.continuity(
        driver,
        ride.ride_id,
        ContinuityCommand(
            command_id=uuid4(),
            expected_session_version=started["version"],
            observation_sequence=6,
            signals=signals(inside_pickup_zone=False),
        ),
        now=NOW + timedelta(seconds=10),
    )
    assert paused["state"] == "wait_paused"
    result = app.evaluate_no_show(
        driver,
        ride.ride_id,
        EvidenceCommand(
            command_id=uuid4(),
            expected_session_version=paused["version"],
            signals=signals(inside_pickup_zone=False),
        ),
        now=NOW + timedelta(seconds=301),
    )
    assert not result["ready"]
    assert app.evidence(rider, ride.ride_id)["ready"] is False
    assert repo.notifications[0]["delivery_status"] == "confirmed"


def test_projections_defaults_ownership_and_landmark_fallback():
    app, repo, ride, landmark = fixture_app()
    rider = subject(ride.rider_id, IdentityType.RIDER)
    assert app.arrival(rider, ride.ride_id) == {"state": "arrival_unverified"}
    assert app.readiness(rider, ride.ride_id) == {"classification": "insufficient_data"}
    assert app.waiting(rider, ride.ride_id, now=NOW) == {
        "state": "not_started",
        "audience": "rider",
    }
    assert app.evidence(rider, ride.ride_id)["responsibility"] == (
        "insufficient_evidence"
    )
    guidance = app.landmark(rider, ride.ride_id, landmark.landmark_id, now=NOW)
    assert guidance["status"] == "verified_guidance"
    assert guidance["named_pickup_points"][0]["kind"] == "main_gate"
    assert guidance["named_pickup_points"][0]["reference_photo"]["reference_id"]
    walking = app.walking_guidance(
        rider,
        ride.ride_id,
        WalkingGuidanceRequest(
            pickup_point_id=landmark.named_pickup_points[0].pickup_point_id,
            rider_position=LocationObservation(
                observed_at=NOW,
                sequence=7,
                latitude_e6=8_979_000,
                longitude_e6=38_798_000,
                accuracy_meters=10,
                speed_cm_per_second=100,
            ),
        ),
        now=NOW,
    )
    assert walking["status"] == "guidance_available"
    assert walking["destination"]["heading_degrees"] == 90
    support = subject(uuid4(), IdentityType.STAFF)
    assert app.waiting(support, ride.ride_id, now=NOW)["audience"] == "support"
    app._landmarks.item = landmark.model_copy(update={"ambiguous": True})
    fallback = app.landmark(rider, ride.ride_id, landmark.landmark_id, now=NOW)
    assert fallback["status"] == "coordinates_fallback"
    intruder = subject(uuid4(), IdentityType.RIDER)
    with pytest.raises(ArrivalWaitingConflict, match="access_denied"):
        app.arrival(intruder, ride.ride_id)
    with pytest.raises(ArrivalWaitingConflict, match="driver_required"):
        app.submit_arrival(rider, ride.ride_id, arrival_command(ride), now=NOW)
    assert repo.arrival is None


class Resolver:
    def __init__(self, value):
        self.value = value

    async def resolve(self, request):
        del request
        return self.value


class Enforcer:
    def enforce(self, request, requirement):
        del request, requirement


class Limiter:
    def consume(self, *, subject, operation):
        del subject, operation
        return RateLimitDecision(allowed=True, remaining=10, retry_after_seconds=0)


def test_disabled_routes_activation_and_authenticated_privacy_projections():
    disabled = create_app(Settings(ENVIRONMENT=AppEnvironment.TEST))
    assert not any(
        "arrival-waiting" in getattr(route, "path", "") for route in disabled.routes
    )
    with pytest.raises(RuntimeError, match="secure dependencies"):
        create_app(
            Settings(ENVIRONMENT=AppEnvironment.TEST, ARRIVAL_WAITING_ENABLED=True)
        )
    with pytest.raises(ValueError, match="separate approval"):
        Settings(ENVIRONMENT=AppEnvironment.PRODUCTION, ARRIVAL_WAITING_ENABLED=True)

    application, _, ride, landmark = fixture_app()
    active = create_app(
        Settings(ENVIRONMENT=AppEnvironment.TEST, ARRIVAL_WAITING_ENABLED=True),
        arrival_waiting=ArrivalWaitingActivation(
            application=application,
            subject_resolver=Resolver(subject(ride.driver_id, IdentityType.DRIVER)),
            authorization_enforcer=Enforcer(),
            rate_limiter=Limiter(),
            metrics=NullMetricsSink(),
        ),
    )
    client = TestClient(active)
    base = f"/api/arrival-waiting/{ride.ride_id}"
    for path in (
        "/arrival",
        "/readiness",
        "/waiting",
        "/countdown",
        "/evidence",
        f"/landmarks/{landmark.landmark_id}",
    ):
        response = client.get(base + path)
        assert response.status_code == 200
        if not path.startswith("/landmarks/"):
            assert "latitude_e6" not in response.text
            assert "longitude_e6" not in response.text
        else:
            assert "exact_stopping_position" in response.text

    oversized = client.post(
        base + "/driver/location",
        content=b"x" * 17_000,
        headers={"content-length": "17000"},
    )
    assert oversized.status_code == 413
