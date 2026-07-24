import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.enforcement import AuthorizationContextMiddleware
from BACKEND.booking.application import BookingApplication, ConfirmBookingCommand
from BACKEND.booking.models import (
    BookingConfirmation,
    BookingConflict,
    BookingQuote,
    ProviderRouteEvidence,
    RoutePreview,
    TollEvidenceState,
    TrafficEvidenceState,
)
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.pricing.models import DataQuality, FareBreakdown, RouteMetrics
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    PickupSafetyStatus,
)
from BACKEND.routes.booking import create_booking_router


class FixedResolver:
    def __init__(self, subject):
        self.subject = subject

    async def resolve(self, request: Request):
        del request
        return self.subject


class CapturingEnforcer:
    def __init__(self):
        self.requirement = None

    def enforce(self, request, requirement):
        del request
        self.requirement = requirement


def preview() -> RoutePreview:
    now = datetime.now(UTC)
    pickup = PickupDefinition(
        coordinate=Coordinate(latitude=9.01, longitude=38.76),
        source=LocationSource.RIDER_SELECTED,
        observed_at=now,
        accuracy_metres=10,
        structured_address="Bole Medhanialem",
        map_confidence_bps=9000,
        safety_status=PickupSafetyStatus.RECOMMENDED,
        policy_version="booking.pickup.v1",
    )
    destination = DestinationDefinition(
        coordinate=Coordinate(latitude=9.02, longitude=38.77),
        source=LocationSource.LANDMARK,
        observed_at=now,
        structured_address="Friendship Mall",
        map_confidence_bps=9000,
    )
    breakdown = FareBreakdown(
        currency="ETB",
        base_minor=1000,
        distance_minor=2000,
        time_minor=1000,
        minimum_adjustment_minor=0,
        tax_placeholder_minor=0,
        rider_total_minor=4000,
        driver_gross_minor=4000,
        ayo_commission_minor=800,
        driver_net_projection_minor=3200,
    )
    route = ProviderRouteEvidence(
        metrics=RouteMetrics(
            distance_meters=5400,
            duration_seconds=900,
            observed_at=now,
            provider_id="test_adapter",
            provider_version="test.v1",
            distance_source="route_intelligence",
            duration_source="route_intelligence",
            provenance_reference="test-evidence-0001",
            data_quality=DataQuality.VERIFIED,
        ),
        geometry=((9.01, 38.76), (9.02, 38.77)),
        origin_accuracy_metres=8,
        destination_accuracy_metres=10,
        map_confidence_bps=9400,
        traffic_state=TrafficEvidenceState.AVAILABLE,
        toll_state=TollEvidenceState.UNKNOWN,
        attribution="Evaluation provider",
    )
    return RoutePreview(
        booking_session_hash="a" * 64,
        pickup=pickup,
        destination=destination,
        service_zone_id=uuid4(),
        service_zone_version="addis.v1",
        service_type="immediate_standard",
        route=route,
        quote=BookingQuote(
            policy_id=uuid4(),
            policy_version="pricing.v1",
            breakdown=breakdown,
            expires_at=now + timedelta(minutes=5),
        ),
        evidence_hash="b" * 64,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )


class FixedApplication:
    def __init__(self, item: RoutePreview):
        self.item = item

    def search_places(self, **kwargs):
        del kwargs
        return ()

    def preview(self, command, **kwargs):
        del command, kwargs
        return self.item

    def confirm(self, command, **kwargs):
        subject = kwargs["subject"]
        item = BookingConfirmation(
            evidence_id=self.item.evidence_id,
            evidence_hash=self.item.evidence_hash,
            quote_id=self.item.quote.quote_id,
            ride_request_id=uuid4(),
            rider_identity_id=subject.identity_id,
            idempotency_key_hash="c" * 64,
            confirmed_at=datetime.now(UTC),
        )
        return item, SimpleNamespace(
            request_id=item.ride_request_id,
            state=SimpleNamespace(value="ready_for_dispatch"),
        )


class FakeUnit:
    def __init__(self, booking):
        self.booking = booking

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeComposition:
    def __init__(self, booking):
        self.booking = booking

    def unit_of_work(self):
        return FakeUnit(self.booking)


class FakeBookingRepository:
    def __init__(self, item, confirmation=None):
        self.item = item
        self.confirmation = confirmation

    def get_preview(self, evidence_id, lock=False):
        del lock
        return self.item if evidence_id == self.item.evidence_id else None

    def get_confirmation_for_evidence(self, evidence_id):
        return self.confirmation if evidence_id == self.item.evidence_id else None


class FakeRideRequests:
    def __init__(self, ride):
        self.ride = ride
        self.create_calls = 0

    def get_owned(self, **kwargs):
        del kwargs
        return self.ride

    def create(self, **kwargs):
        del kwargs
        self.create_calls += 1
        return self.ride


class FlakyDispatch:
    def __init__(self):
        self.calls = 0

    def start(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("route_intelligence_timeout")


def client(subject):
    item = preview()
    resolver = FixedResolver(subject)
    enforcer = CapturingEnforcer()
    app = FastAPI()
    app.state.authorization_enforcer = enforcer
    app.include_router(
        create_booking_router(FixedApplication(item), resolver), prefix="/api"
    )
    app.add_middleware(AuthorizationContextMiddleware, resolver=resolver)
    return TestClient(app), item, enforcer


def test_guest_preview_exposes_transparent_unknown_toll_without_zero():
    api, item, _ = client(None)
    response = api.post(
        "/api/mobile/booking/route-previews",
        json={
            "client_preview_id": str(uuid4()),
            "booking_session": "s" * 32,
            "pickup": item.pickup.model_dump(mode="json"),
            "destination": item.destination.model_dump(mode="json"),
            "service_type": "immediate_standard",
        },
    )
    assert response.status_code == 200
    assert response.json()["toll_message"] == "Toll information unavailable."
    assert response.json()["toll_amount_minor"] is None
    assert response.json()["estimated_fare_minor"] == 4000
    assert response.json()["surge_applied"] is False


def test_confirmation_requires_identity_and_authorization_permission():
    api, item, _ = client(None)
    payload = {
        "evidence_id": str(item.evidence_id),
        "evidence_hash": item.evidence_hash,
        "quote_id": str(item.quote.quote_id),
        "booking_session": "s" * 32,
        "client_request_id": str(uuid4()),
        "consent_policy_version": "booking.consent.v1",
    }
    assert (
        api.post(
            "/api/mobile/booking/confirm",
            json=payload,
            headers={"Idempotency-Key": "booking-confirm-0001"},
        ).status_code
        == 401
    )

    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    api, item, enforcer = client(rider)
    payload.update(
        {
            "evidence_id": str(item.evidence_id),
            "evidence_hash": item.evidence_hash,
            "quote_id": str(item.quote.quote_id),
        }
    )
    response = api.post(
        "/api/mobile/booking/confirm",
        json=payload,
        headers={"Idempotency-Key": "booking-confirm-0001"},
    )
    assert response.status_code == 201
    assert response.json()["dispatch_started"] is False
    assert response.json()["state"] == "ready_for_dispatch"
    assert enforcer.requirement.permission == "ride_request.create"


def test_toll_model_never_allows_unknown_zero():
    item = preview()
    with pytest.raises(ValidationError, match="forbidden"):
        ProviderRouteEvidence(**{**item.route.model_dump(), "toll_amount_minor": 0})


def test_booking_activation_defaults_off_and_production_fails_closed():
    assert Settings(_env_file=None).RIDER_BOOKING_ENABLED is False
    with pytest.raises(ValidationError, match="production activation"):
        Settings(
            _env_file=None,
            ENVIRONMENT=AppEnvironment.PRODUCTION,
            RIDER_BOOKING_ENABLED=True,
        )


def test_backend_rejects_expired_route_evidence_before_creating_ride():
    now = datetime.now(UTC)
    item = preview()
    expired_quote = item.quote.model_copy(
        update={"expires_at": now - timedelta(seconds=1)}
    )
    item = item.model_copy(
        update={
            "quote": expired_quote,
            "booking_session_hash": hashlib.sha256(("s" * 32).encode()).hexdigest(),
            "created_at": now - timedelta(minutes=5),
            "expires_at": now - timedelta(seconds=1),
        }
    )
    rides = FakeRideRequests(SimpleNamespace())
    application = BookingApplication(
        FakeComposition(FakeBookingRepository(item)),
        SimpleNamespace(),
        SimpleNamespace(),
        rides,
        uuid4(),
    )
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session="s" * 32,
        client_request_id=uuid4(),
        idempotency_key="booking-confirm-expired",
        consent_policy_version="booking.consent.v1",
    )
    with pytest.raises(BookingConflict, match="route_evidence_expired"):
        application.confirm(command, subject=rider, at=now)
    assert rides.create_calls == 0


def test_backend_duplicate_confirmation_returns_same_canonical_request():
    item = preview()
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    key = "booking-confirm-stable"
    confirmation = BookingConfirmation(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        ride_request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
        confirmed_at=datetime.now(UTC),
    )
    ride = SimpleNamespace(request_id=confirmation.ride_request_id)
    rides = FakeRideRequests(ride)
    application = BookingApplication(
        FakeComposition(FakeBookingRepository(item, confirmation)),
        SimpleNamespace(),
        SimpleNamespace(),
        rides,
        uuid4(),
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session="s" * 32,
        client_request_id=uuid4(),
        idempotency_key=key,
        consent_policy_version="booking.consent.v1",
    )
    stored, returned_ride = application.confirm(
        command, subject=rider, at=datetime.now(UTC)
    )
    assert stored == confirmation
    assert returned_ride is ride
    assert rides.create_calls == 0


def test_persisted_booking_retries_same_dispatch_handoff_after_provider_timeout():
    item = preview()
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    key = "booking-dispatch-retry"
    confirmation = BookingConfirmation(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        ride_request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
        confirmed_at=datetime.now(UTC),
    )
    ride = SimpleNamespace(request_id=confirmation.ride_request_id)
    dispatch = FlakyDispatch()
    application = BookingApplication(
        FakeComposition(FakeBookingRepository(item, confirmation)),
        SimpleNamespace(),
        SimpleNamespace(),
        FakeRideRequests(ride),
        uuid4(),
        dispatch,
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session="s" * 32,
        client_request_id=uuid4(),
        idempotency_key=key,
        consent_policy_version="booking.consent.v1",
    )
    with pytest.raises(BookingConflict, match="temporarily_unavailable"):
        application.confirm(command, subject=rider, at=datetime.now(UTC))
    stored, returned = application.confirm(command, subject=rider, at=datetime.now(UTC))
    assert stored == confirmation and returned is ride
    assert dispatch.calls == 2
