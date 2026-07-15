from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.main import ScheduledDispatchActivation, create_app
from BACKEND.observability import InMemoryMetricsSink
from BACKEND.rate_limit.models import RateLimitDecision
from BACKEND.scheduled.integration_models import PublicReservation

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
            allowed=True,
            remaining=Decimal(4),
            retry_after_seconds=0,
        )


class Application:
    def __init__(self):
        self.seen_subject = None

    def create(self, subject, command, *, idempotency_key, now):
        del idempotency_key, now
        self.seen_subject = subject
        return (
            PublicReservation(
                reservation_id=uuid4(),
                state="accepted",
                pickup_place_id=command.pickup_place_id,
                destination_place_id=command.destination_place_id,
                service_type=command.service_type,
                requested_pickup_at=command.requested_pickup_at,
                requested_timezone=command.requested_timezone,
                version=1,
                requires_passenger_confirmation=False,
            ),
            True,
        )

    def read(self, subject, reservation_id):
        del subject, reservation_id
        raise AssertionError("Unauthenticated request reached application")


_DEFAULT = object()


def client(subject=_DEFAULT):
    identity = (
        AuthorizationSubject(
            identity_id=uuid4(),
            identity_type=IdentityType.RIDER,
            actor_type=ActorType.RIDER,
        )
        if subject is _DEFAULT
        else subject
    )
    application = Application()
    activation = ScheduledDispatchActivation(
        application=application,
        subject_resolver=Resolver(identity),
        authorization_enforcer=Enforcer(),
        rate_limiter=Limiter(),
        metrics=InMemoryMetricsSink(),
    )
    settings = Settings(
        ENVIRONMENT=AppEnvironment.TEST,
        DISPATCH_ENABLED=False,
        SCHEDULED_DISPATCH_ENABLED=True,
    )
    return (
        TestClient(create_app(settings, scheduled_dispatch=activation)),
        application,
        identity,
    )


def test_authenticated_subject_is_server_derived_and_public_response_is_sanitized():
    http, application, identity = client()
    response = http.post(
        "/api/scheduled/reservations",
        headers={"Idempotency-Key": "scheduled-api-retry-0001"},
        json={
            "pickup_place_id": "place.addis.bole",
            "destination_place_id": "place.addis.saris",
            "service_type": "ayo.go",
            "quote_id": str(uuid4()),
            "requested_pickup_at": (NOW + timedelta(days=1)).isoformat(),
            "requested_timezone": "Africa/Addis_Ababa",
            "passenger_channel": "identity",
        },
    )
    assert response.status_code == 201
    assert application.seen_subject.identity_id == identity.identity_id
    assert set(response.json()) == {
        "reservation_id",
        "state",
        "pickup_place_id",
        "destination_place_id",
        "service_type",
        "requested_pickup_at",
        "requested_timezone",
        "version",
        "requires_passenger_confirmation",
    }


def test_caller_supplied_booker_driver_and_role_fields_are_rejected():
    http, _, _ = client()
    base = {
        "pickup_place_id": "place.addis.bole",
        "destination_place_id": "place.addis.saris",
        "service_type": "ayo.go",
        "quote_id": str(uuid4()),
        "requested_pickup_at": (NOW + timedelta(days=1)).isoformat(),
        "requested_timezone": "Africa/Addis_Ababa",
        "passenger_channel": "identity",
    }
    for injected in (
        {"booker_id": str(uuid4())},
        {"driver_id": str(uuid4())},
        {"role": "administrator"},
    ):
        response = http.post(
            "/api/scheduled/reservations",
            headers={"Idempotency-Key": "scheduled-api-retry-0002"},
            json={**base, **injected},
        )
        assert response.status_code == 422
        assert response.json() == {"error": {"code": "validation_failed"}}


def test_missing_authentication_fails_closed():
    http, _, _ = client(subject=None)
    response = http.get(f"/api/scheduled/reservations/{uuid4()}")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_required"}}
