from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from BACKEND.active_ride.application import ActiveRideApplication
from BACKEND.active_ride.models import ActiveRide, ActiveRideState
from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.main import ActiveRideActivation, create_app
from BACKEND.observability import InMemoryMetricsSink
from BACKEND.rate_limit.models import RateLimitDecision

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


class Resolver:
    def __init__(self, subject):
        self.subject = subject

    async def resolve(self, request):
        del request
        return self.subject


class Enforcer:
    def enforce(self, request, requirement):
        del request, requirement


class Limiter:
    def consume(self, *, subject, operation):
        del subject, operation
        return RateLimitDecision(
            allowed=True, remaining=Decimal(10), retry_after_seconds=0
        )


def client(composition, subject):
    activation = ActiveRideActivation(
        application=ActiveRideApplication(
            composition.unit_of_work, pin_secret=b"x" * 32
        ),
        subject_resolver=Resolver(subject),
        authorization_enforcer=Enforcer(),
        rate_limiter=Limiter(),
        metrics=InMemoryMetricsSink(),
    )
    return TestClient(
        create_app(
            Settings(ENVIRONMENT=AppEnvironment.TEST, ACTIVE_RIDE_ENABLED=True),
            active_ride=activation,
        )
    )


def test_authenticated_api_snapshot_command_replay_and_ownership(postgres_composition):
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
    rider = AuthorizationSubject(
        identity_id=rider_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    driver = AuthorizationSubject(
        identity_id=driver_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )
    rider_http, driver_http = (
        client(postgres_composition, rider),
        client(postgres_composition, driver),
    )
    snapshot = rider_http.get(f"/api/active-rides/{ride_id}")
    assert snapshot.status_code == 200
    assert "destination_place_id" not in snapshot.json()
    command_id = uuid4()
    body = {"command_id": str(command_id), "expected_version": 1}
    first = driver_http.post(f"/api/active-rides/{ride_id}/driver/en-route", json=body)
    duplicate = driver_http.post(
        f"/api/active-rides/{ride_id}/driver/en-route", json=body
    )
    assert first.status_code == duplicate.status_code == 200
    assert duplicate.json()["command_created"] is False
    replay = rider_http.get(f"/api/active-rides/{ride_id}/events?after=0")
    assert [event["sequence"] for event in replay.json()["events"]] == [1, 2]
    gap = rider_http.get(f"/api/active-rides/{ride_id}/events?after=99")
    assert gap.status_code == 409
    assert gap.json() == {"error": {"code": "resync_required"}}
    forbidden = rider_http.post(
        f"/api/active-rides/{ride_id}/driver/arrived",
        json={"command_id": str(uuid4()), "expected_version": 2},
    )
    assert forbidden.status_code == 403


def test_caller_identity_and_unknown_fields_are_rejected(postgres_composition):
    driver = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )
    response = client(postgres_composition, driver).post(
        f"/api/active-rides/{uuid4()}/driver/en-route",
        json={
            "command_id": str(uuid4()),
            "expected_version": 1,
            "driver_id": str(uuid4()),
            "role": "administrator",
        },
    )
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "validation_failed"}}
