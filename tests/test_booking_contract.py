import hashlib
from concurrent.futures import ThreadPoolExecutor
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
from BACKEND.booking.application import (
    BookingApplication,
    ConfirmBookingCommand,
    PreviewRouteCommand,
)
from BACKEND.booking.consent import ImmutableBookingConsentRegistry
from BACKEND.booking.models import (
    BookingConfirmation,
    BookingConflict,
    BookingConsentMetadata,
    BookingQuote,
    ProviderRouteEvidence,
    RoutePreview,
    TollEvidenceState,
    TrafficEvidenceState,
)
from BACKEND.config.settings import AppEnvironment, Settings
from BACKEND.identity.models import IdentityType
from BACKEND.pricing.models import DataQuality, FareBreakdown, RouteMetrics
from BACKEND.ride_request.application import RideRequestAccessDenied
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    PickupSafetyStatus,
    RideRequestState,
    RideServiceType,
)
from BACKEND.routes.booking import ConfirmBookingRequest, create_booking_router


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
        consent=consent_policy(now=now),
        evidence_hash="b" * 64,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def consent_policy(
    *,
    now: datetime | None = None,
    version: str = "booking.consent.v1",
    content_hash: str = "e" * 64,
) -> BookingConsentMetadata:
    effective = now or datetime.now(UTC)
    return BookingConsentMetadata(
        required_version=version,
        document_id="booking.immediate-standard",
        content_hash=content_hash,
        effective_from=effective - timedelta(days=1),
        effective_until=effective + timedelta(days=1),
        acknowledgment_required=True,
    )


def consent_registry(item: RoutePreview) -> ImmutableBookingConsentRegistry:
    assert item.consent is not None
    return ImmutableBookingConsentRegistry((item.consent,))


class FixedApplication:
    def __init__(self, item: RoutePreview):
        self.item = item
        self.confirmation = None
        self.ride = None

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
            fare_estimate_id=uuid4(),
            estimate_acceptance_id=uuid4(),
            pricing_lineage_hash="d" * 64,
            rider_identity_id=subject.identity_id,
            idempotency_key_hash="c" * 64,
            confirmed_at=datetime.now(UTC),
        )
        ride = SimpleNamespace(
            request_id=item.ride_request_id,
            state=SimpleNamespace(value="ready_for_dispatch"),
        )
        self.confirmation = item
        self.ride = ride
        return item, ride

    def recover_confirmation(self, *, subject, client_request_id):
        del client_request_id
        if (
            self.confirmation is None
            or self.confirmation.rider_identity_id != subject.identity_id
        ):
            raise BookingConflict("booking_confirmation_not_found")
        return self.confirmation, self.ride


class FakeUnit:
    def __init__(self, booking, ride_requests=None):
        self.booking = booking
        self.ride_requests = ride_requests

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeComposition:
    def __init__(self, booking, ride_requests=None):
        self.booking = booking
        self.ride_requests = ride_requests

    def unit_of_work(self):
        return FakeUnit(self.booking, self.ride_requests)


class FakeBookingRepository:
    def __init__(self, item, confirmation=None):
        self.item = item
        self.confirmation = confirmation
        self.add_confirmation_calls = 0

    def get_preview(self, evidence_id, lock=False):
        del lock
        return (
            self.item
            if self.item is not None and evidence_id == self.item.evidence_id
            else None
        )

    def get_confirmation_for_evidence(self, evidence_id):
        return self.confirmation if evidence_id == self.item.evidence_id else None

    def get_confirmation_for_idempotency_key_hash(
        self, *, rider_identity_id, idempotency_key_hash
    ):
        if (
            self.confirmation is None
            or self.confirmation.rider_identity_id != rider_identity_id
            or self.confirmation.idempotency_key_hash != idempotency_key_hash
        ):
            return None
        return self.confirmation

    def get_confirmation_for_client_request(
        self, *, rider_identity_id, client_request_id
    ):
        del client_request_id
        if (
            self.confirmation is None
            or self.confirmation.rider_identity_id != rider_identity_id
        ):
            return None
        return self.confirmation

    def add_confirmation(self, item):
        self.add_confirmation_calls += 1
        self.confirmation = item
        return item

    def add_preview(self, item):
        self.item = item
        return item


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


class DenyingRideRequests(FakeRideRequests):
    def get_owned(self, **kwargs):
        del kwargs
        raise RideRequestAccessDenied("private rider and request mismatch")


class FakePricingAuthority:
    def __init__(self):
        self.calls = 0
        self.estimate_id = uuid4()
        self.acceptance_id = uuid4()
        self.lineage_hash = "d" * 64

    def establish_canonical_lineage(self, **kwargs):
        del kwargs
        self.calls += 1
        return (
            SimpleNamespace(estimate_id=self.estimate_id),
            SimpleNamespace(acceptance_id=self.acceptance_id),
            self.lineage_hash,
        )

    def quote(self, **kwargs):
        at = kwargs["at"]
        item = preview()
        return item.quote.model_copy(update={"expires_at": at + timedelta(minutes=5)})


class PreviewRideRequests:
    def __init__(self, zone_id):
        self.zone = SimpleNamespace(
            zone_id=zone_id,
            version="addis.v1",
            supported_service_types={RideServiceType.IMMEDIATE_STANDARD},
        )

    def find_zone(self, **kwargs):
        del kwargs
        return self.zone


class PreviewRoutes:
    def __init__(self, item):
        self.item = item

    def route(self, **kwargs):
        del kwargs
        return self.item.route


class FailingConsentAuthority:
    def required_policy(self, *, at: datetime) -> BookingConsentMetadata:
        del at
        raise BookingConflict("private consent authority state")

    def policy_for_version(self, version: str) -> BookingConsentMetadata | None:
        del version
        raise BookingConflict("private consent authority state")


class CountingDispatch:
    def __init__(self):
        self.calls = 0

    def start(self, **kwargs):
        del kwargs
        self.calls += 1


class FlakyDispatch:
    def __init__(self):
        self.calls = 0

    def start(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("route_intelligence_timeout")


def first_confirmation_scenario():
    booking_session = "s" * 32
    item = preview().model_copy(
        update={
            "booking_session_hash": hashlib.sha256(booking_session.encode()).hexdigest()
        }
    )
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    client_request_id = uuid4()
    ride = SimpleNamespace(
        request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        client_request_id=client_request_id,
        consent_policy_version="booking.consent.v1",
        state=RideRequestState.READY_FOR_DISPATCH,
    )
    repository = FakeBookingRepository(item)
    rides = FakeRideRequests(ride)
    pricing = FakePricingAuthority()
    dispatch = CountingDispatch()
    application = BookingApplication(
        FakeComposition(repository),
        SimpleNamespace(),
        pricing,
        rides,
        item.quote.policy_id,
        dispatch,
        consent=consent_registry(item),
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session=booking_session,
        client_request_id=client_request_id,
        idempotency_key="booking-confirm-consent",
        consent_policy_version="booking.consent.v1",
        consent_document_hash=item.consent.content_hash,
        consent_acknowledged=True,
    )
    return application, command, rider, item, repository, rides, pricing, dispatch


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
    assert response.json()["consent"] == {
        "required_version": "booking.consent.v1",
        "document_id": "booking.immediate-standard",
        "content_hash": "e" * 64,
        "acknowledgment_required": True,
    }


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
    assert response.json()["fare_estimate_id"]
    assert response.json()["estimate_acceptance_id"]
    assert response.json()["pricing_lineage_hash"] == "d" * 64
    assert response.json()["next_step"] == "check_dispatch_status"
    assert enforcer.requirement.permission == "ride_request.create"


def test_lost_confirmation_response_recovers_by_rider_owned_client_request_id():
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    api, item, enforcer = client(rider)
    client_request_id = uuid4()
    payload = {
        "evidence_id": str(item.evidence_id),
        "evidence_hash": item.evidence_hash,
        "quote_id": str(item.quote.quote_id),
        "booking_session": "s" * 32,
        "client_request_id": str(client_request_id),
        "consent_policy_version": "booking.consent.v1",
    }
    created = api.post(
        "/api/mobile/booking/confirm",
        json=payload,
        headers={"Idempotency-Key": "booking-confirm-recovery-0001"},
    )
    recovered = api.get(
        f"/api/mobile/booking/confirmations/by-client-request/{client_request_id}"
    )
    assert created.status_code == 201
    assert recovered.status_code == 200
    assert recovered.json() == created.json()
    assert set(recovered.json()) == {
        "confirmation_id",
        "ride_request_id",
        "fare_estimate_id",
        "estimate_acceptance_id",
        "pricing_lineage_hash",
        "state",
        "dispatch_started",
        "next_step",
    }
    assert enforcer.requirement.permission == "ride_request.read_own"


def test_confirmation_recovery_is_authenticated_and_cross_rider_safe():
    client_request_id = uuid4()
    anonymous, _, _ = client(None)
    assert (
        anonymous.get(
            f"/api/mobile/booking/confirmations/by-client-request/{client_request_id}"
        ).status_code
        == 401
    )

    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    api, _, _ = client(rider)
    response = api.get(
        f"/api/mobile/booking/confirmations/by-client-request/{client_request_id}"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "booking_confirmation_not_found"}}


def test_public_confirmation_fails_closed_without_complete_pricing_lineage():
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    item = preview()

    class IncompleteLineageApplication(FixedApplication):
        def confirm(self, command, **kwargs):
            confirmation, ride = super().confirm(command, **kwargs)
            return (
                confirmation.model_copy(
                    update={
                        "fare_estimate_id": None,
                        "estimate_acceptance_id": None,
                        "pricing_lineage_hash": None,
                    }
                ),
                ride,
            )

    resolver = FixedResolver(rider)
    api = FastAPI()
    api.state.authorization_enforcer = CapturingEnforcer()
    api.include_router(
        create_booking_router(IncompleteLineageApplication(item), resolver),
        prefix="/api",
    )
    api.add_middleware(AuthorizationContextMiddleware, resolver=resolver)
    response = TestClient(api).post(
        "/api/mobile/booking/confirm",
        json={
            "evidence_id": str(item.evidence_id),
            "evidence_hash": item.evidence_hash,
            "quote_id": str(item.quote.quote_id),
            "booking_session": "s" * 32,
            "client_request_id": str(uuid4()),
            "consent_policy_version": "booking.consent.v1",
        },
        headers={"Idempotency-Key": "booking-confirm-lineage-0001"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "pricing_unavailable"}}


def test_toll_model_never_allows_unknown_zero():
    item = preview()
    with pytest.raises(ValidationError, match="forbidden"):
        ProviderRouteEvidence(**{**item.route.model_dump(), "toll_amount_minor": 0})


def preview_application(*, policies=None):
    item = preview()
    repository = FakeBookingRepository(item=None)
    authority = (
        None if policies is None else ImmutableBookingConsentRegistry(tuple(policies))
    )
    application = BookingApplication(
        FakeComposition(repository, PreviewRideRequests(item.service_zone_id)),
        PreviewRoutes(item),
        FakePricingAuthority(),
        FakeRideRequests(SimpleNamespace()),
        item.quote.policy_id,
        consent=authority,
    )
    command = PreviewRouteCommand(
        client_preview_id=uuid4(),
        booking_session="s" * 32,
        pickup=item.pickup,
        destination=item.destination,
    )
    return application, command, repository


def test_preview_returns_server_owned_consent_and_binds_evidence_hash():
    now = datetime.now(UTC)
    policy = consent_policy(now=now)
    application, command, _ = preview_application(policies=(policy,))

    first = application.preview(command, subject=None, at=now)
    assert first.consent == policy

    changed = consent_policy(now=now, content_hash="f" * 64)
    other, other_command, _ = preview_application(policies=(changed,))
    second = other.preview(
        other_command.model_copy(
            update={"client_preview_id": command.client_preview_id}
        ),
        subject=None,
        at=now,
    )
    assert first.evidence_hash != second.evidence_hash


def test_preview_policy_is_not_client_selectable_and_absence_fails_closed():
    application, command, _ = preview_application(policies=None)
    with pytest.raises(BookingConflict, match="consent_policy_unavailable"):
        application.preview(command, subject=None, at=datetime.now(UTC))
    with pytest.raises(ValidationError, match="extra"):
        PreviewRouteCommand(
            **command.model_dump(), consent_policy_version="invented.v1"
        )


def test_consent_registry_rejects_duplicate_ambiguous_and_invalid_intervals():
    now = datetime.now(UTC)
    policy = consent_policy(now=now)
    with pytest.raises(BookingConflict, match="consent_policy_unavailable"):
        ImmutableBookingConsentRegistry((policy, policy))
    overlapping = consent_policy(now=now, version="booking.consent.v2")
    with pytest.raises(BookingConflict, match="consent_policy_unavailable"):
        ImmutableBookingConsentRegistry((policy, overlapping)).required_policy(at=now)
    with pytest.raises(ValidationError, match="interval"):
        BookingConsentMetadata(
            **policy.model_dump(exclude={"effective_until"}),
            effective_until=policy.effective_from,
        )


def test_consent_metadata_validates_optional_interval_and_authority_invariants():
    now = datetime.now(UTC)
    open_ended = BookingConsentMetadata(
        required_version="booking.consent.open-ended.v1",
        document_id="booking.immediate-standard",
        content_hash="e" * 64,
        effective_from=now,
        effective_until=None,
        acknowledgment_required=True,
    )
    assert open_ended.effective_until is None

    for update in (
        {"effective_from": now.replace(tzinfo=None)},
        {"effective_until": (now + timedelta(days=1)).replace(tzinfo=None)},
        {"acknowledgment_required": False},
    ):
        with pytest.raises(ValidationError):
            BookingConsentMetadata.model_validate({**open_ended.model_dump(), **update})


def test_confirmation_authority_failure_is_generic_and_side_effect_free():
    application, command, rider, _, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    application._consent = FailingConsentAuthority()

    with pytest.raises(BookingConflict) as raised:
        application.confirm(command, subject=rider, at=datetime.now(UTC))

    assert str(raised.value) == "consent_policy_changed"
    assert "private" not in str(raised.value)
    assert "version" not in str(raised.value)
    assert "hash" not in str(raised.value)
    assert rides.create_calls == 0
    assert pricing.calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


@pytest.mark.parametrize(
    "updates",
    (
        {"consent_acknowledged": None},
        {"consent_acknowledged": False},
        {"consent_policy_version": None},
        {"consent_policy_version": "malformed value"},
        {"consent_policy_version": "booking.consent.unknown"},
        {"consent_document_hash": None},
        {"consent_document_hash": "altered"},
    ),
)
def test_consent_rejection_is_generic_and_side_effect_free(updates):
    application, command, rider, _, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    with pytest.raises(BookingConflict) as raised:
        application.confirm(
            command.model_copy(update=updates), subject=rider, at=datetime.now(UTC)
        )
    assert str(raised.value) == "consent_policy_changed"
    assert rides.create_calls == 0
    assert pricing.calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


@pytest.mark.parametrize(
    "value",
    (1, 0, "true", "false", "yes", "on", [], {}, [True]),
)
def test_consent_acknowledgment_rejects_non_boolean_values_before_dispatch(value):
    application, command, rider, _, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    request_payload = {
        **command.model_dump(exclude={"idempotency_key"}),
        "consent_acknowledged": value,
    }
    with pytest.raises(ValidationError):
        ConfirmBookingRequest.model_validate(request_payload)
    with pytest.raises(ValidationError):
        ConfirmBookingCommand.model_validate(
            {**command.model_dump(), "consent_acknowledged": value}
        )
    assert rides.create_calls == 0
    assert pricing.calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


def test_consent_acknowledgment_public_schema_is_boolean_and_true_is_accepted():
    schema = ConfirmBookingRequest.model_json_schema()
    acknowledgment = schema["properties"]["consent_acknowledged"]
    assert {item.get("type") for item in acknowledgment["anyOf"]} == {
        "boolean",
        "null",
    }
    application, command, rider, _, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    parsed = ConfirmBookingRequest.model_validate(
        command.model_dump(exclude={"idempotency_key"})
    )
    confirmation, _ = application.confirm(
        command.model_copy(update=parsed.model_dump()),
        subject=rider,
        at=datetime.now(UTC),
    )
    assert confirmation == repository.confirmation
    assert rides.create_calls == 1
    assert pricing.calls == 1
    assert repository.add_confirmation_calls == 1
    assert dispatch.calls == 1


def test_mandatory_rotation_rejects_old_preview_and_new_preview_uses_new_policy():
    application, command, rider, item, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    now = datetime.now(UTC)
    assert item.consent is not None
    old = item.consent.model_copy(update={"effective_until": now})
    rotated = BookingConsentMetadata(
        required_version="booking.consent.v2",
        document_id="booking.immediate-standard",
        content_hash="f" * 64,
        effective_from=now,
        effective_until=now + timedelta(days=1),
        acknowledgment_required=True,
    )
    application._consent = ImmutableBookingConsentRegistry((old, rotated))
    with pytest.raises(BookingConflict, match="consent_policy_changed"):
        application.confirm(command, subject=rider, at=now)
    assert (
        rides.create_calls,
        pricing.calls,
        repository.add_confirmation_calls,
        dispatch.calls,
    ) == (0, 0, 0, 0)

    preview_app, preview_command, _ = preview_application(policies=(rotated,))
    fresh = preview_app.preview(preview_command, subject=rider, at=now)
    assert fresh.consent == rotated


def test_legacy_unbound_preview_cannot_receive_a_guessed_policy():
    application, command, rider, item, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    repository.item = item.model_copy(update={"consent": None})
    with pytest.raises(BookingConflict, match="consent_policy_changed"):
        application.confirm(command, subject=rider, at=datetime.now(UTC))
    assert (
        rides.create_calls,
        pricing.calls,
        repository.add_confirmation_calls,
        dispatch.calls,
    ) == (0, 0, 0, 0)


def test_successful_consent_uses_server_time_and_preserves_replay_and_recovery():
    application, command, rider, item, repository, rides, pricing, dispatch = (
        first_confirmation_scenario()
    )
    server_time = datetime.now(UTC)
    confirmation, ride = application.confirm(command, subject=rider, at=server_time)
    assert ride.consent_policy_version == item.consent.required_version
    assert confirmation.confirmed_at == server_time
    replayed = application.confirm(command, subject=rider, at=server_time)
    assert replayed == (confirmation, ride)
    assert application.recover_confirmation(
        subject=rider, client_request_id=command.client_request_id
    ) == (confirmation, ride)
    assert rides.create_calls == 1
    assert pricing.calls == 1
    assert repository.add_confirmation_calls == 1
    assert dispatch.calls == 2


@pytest.mark.parametrize(
    "field,value",
    (
        ("consent_policy_version", "booking.consent.v2"),
        ("consent_document_hash", "f" * 64),
    ),
)
def test_canonical_replay_consent_change_is_generic(field, value):
    application, command, rider, _, _, repository, rides, dispatch = replay_scenario()
    with pytest.raises(BookingConflict) as raised:
        application.confirm(
            command.model_copy(update={field: value}),
            subject=rider,
            at=datetime.now(UTC),
        )
    assert str(raised.value) == "idempotency_conflict"
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


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
        consent=consent_registry(item),
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
        consent_document_hash=item.consent.content_hash,
        consent_acknowledged=True,
    )
    with pytest.raises(BookingConflict, match="route_evidence_expired"):
        application.confirm(command, subject=rider, at=now)
    assert rides.create_calls == 0


def replay_scenario():
    booking_session = "s" * 32
    item = preview().model_copy(
        update={
            "booking_session_hash": hashlib.sha256(booking_session.encode()).hexdigest()
        }
    )
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    key = "booking-confirm-stable"
    client_request_id = uuid4()
    consent_policy_version = "booking.consent.v1"
    confirmation = BookingConfirmation(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        ride_request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
        confirmed_at=datetime.now(UTC),
    )
    ride = SimpleNamespace(
        request_id=confirmation.ride_request_id,
        rider_identity_id=rider.identity_id,
        client_request_id=client_request_id,
        consent_policy_version=consent_policy_version,
    )
    rides = FakeRideRequests(ride)
    repository = FakeBookingRepository(item, confirmation)
    dispatch = CountingDispatch()
    application = BookingApplication(
        FakeComposition(repository),
        SimpleNamespace(),
        SimpleNamespace(),
        rides,
        uuid4(),
        dispatch,
        consent=consent_registry(item),
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session=booking_session,
        client_request_id=client_request_id,
        idempotency_key=key,
        consent_policy_version=consent_policy_version,
        consent_document_hash=item.consent.content_hash,
        consent_acknowledged=True,
    )
    return application, command, rider, confirmation, ride, repository, rides, dispatch


def test_backend_duplicate_confirmation_returns_same_canonical_request():
    (
        application,
        command,
        rider,
        confirmation,
        ride,
        repository,
        rides,
        dispatch,
    ) = replay_scenario()
    stored, returned_ride = application.confirm(
        command, subject=rider, at=datetime.now(UTC)
    )
    assert stored == confirmation
    assert returned_ride is ride
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 1


def test_canonical_replay_access_denial_is_generic_and_side_effect_free():
    application, command, rider, _, ride, repository, _, dispatch = replay_scenario()
    rides = DenyingRideRequests(ride)
    application._ride_requests = rides

    with pytest.raises(BookingConflict) as raised:
        application.confirm(command, subject=rider, at=datetime.now(UTC))

    assert str(raised.value) == "idempotency_conflict"
    assert all(
        detail not in str(raised.value)
        for detail in (
            str(rider.identity_id),
            str(ride.request_id),
            str(command.evidence_id),
            command.idempotency_key,
            "private rider and request mismatch",
        )
    )
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


def test_first_confirmation_returns_persisted_canonical_result_once():
    booking_session = "s" * 32
    item = preview().model_copy(
        update={
            "booking_session_hash": hashlib.sha256(booking_session.encode()).hexdigest()
        }
    )
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    client_request_id = uuid4()
    ride = SimpleNamespace(
        request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        client_request_id=client_request_id,
        consent_policy_version="booking.consent.v1",
        state=RideRequestState.READY_FOR_DISPATCH,
    )
    repository = FakeBookingRepository(item)
    rides = FakeRideRequests(ride)
    pricing = FakePricingAuthority()
    dispatch = CountingDispatch()
    application = BookingApplication(
        FakeComposition(repository),
        SimpleNamespace(),
        pricing,
        rides,
        item.quote.policy_id,
        dispatch,
        consent=consent_registry(item),
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session=booking_session,
        client_request_id=client_request_id,
        idempotency_key="booking-confirm-first-time",
        consent_policy_version="booking.consent.v1",
        consent_document_hash=item.consent.content_hash,
        consent_acknowledged=True,
    )

    confirmation, returned_ride = application.confirm(
        command, subject=rider, at=datetime.now(UTC)
    )

    assert confirmation is repository.confirmation
    assert returned_ride is ride
    assert confirmation.ride_request_id == ride.request_id
    assert confirmation.fare_estimate_id == pricing.estimate_id
    assert confirmation.estimate_acceptance_id == pricing.acceptance_id
    assert confirmation.pricing_lineage_hash == pricing.lineage_hash
    assert rides.create_calls == 1
    assert pricing.calls == 1
    assert repository.add_confirmation_calls == 1
    assert dispatch.calls == 1


@pytest.mark.parametrize(
    "field,value",
    (
        ("evidence_id", uuid4()),
        ("evidence_hash", "c" * 64),
        ("quote_id", uuid4()),
        ("booking_session", "t" * 32),
        ("client_request_id", uuid4()),
        ("consent_policy_version", "booking.consent.v2"),
        ("idempotency_key", "booking-confirm-changed"),
    ),
)
def test_confirmation_replay_requires_every_immutable_field(field, value):
    application, command, rider, _, _, repository, rides, dispatch = replay_scenario()

    with pytest.raises(BookingConflict) as raised:
        application.confirm(
            command.model_copy(update={field: value}),
            subject=rider,
            at=datetime.now(UTC),
        )

    assert str(raised.value) == "idempotency_conflict"
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


def test_confirmation_replay_is_rider_scoped_and_fails_closed():
    application, command, rider, _, _, repository, rides, dispatch = replay_scenario()
    other_rider = rider.model_copy(update={"identity_id": uuid4()})

    with pytest.raises(BookingConflict) as raised:
        application.confirm(command, subject=other_rider, at=datetime.now(UTC))

    assert str(raised.value) == "idempotency_conflict"
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


def test_concurrent_exact_replays_return_one_canonical_confirmation():
    application, command, rider, confirmation, ride, repository, rides, dispatch = (
        replay_scenario()
    )

    def replay(_):
        return application.confirm(command, subject=rider, at=datetime.now(UTC))

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(executor.map(replay, range(8)))

    assert all(item == (confirmation, ride) for item in results)
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 8


def test_concurrent_conflicting_replays_never_return_canonical_success():
    application, command, rider, _, _, repository, rides, dispatch = replay_scenario()
    conflict = command.model_copy(update={"evidence_id": uuid4()})

    def replay(_):
        with pytest.raises(BookingConflict) as raised:
            application.confirm(conflict, subject=rider, at=datetime.now(UTC))
        return str(raised.value)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(executor.map(replay, range(8)))

    assert results == ("idempotency_conflict",) * 8
    assert rides.create_calls == 0
    assert repository.add_confirmation_calls == 0
    assert dispatch.calls == 0


def test_application_recovers_only_the_authenticated_riders_confirmation():
    item = preview()
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    confirmation = BookingConfirmation(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        ride_request_id=uuid4(),
        fare_estimate_id=uuid4(),
        estimate_acceptance_id=uuid4(),
        pricing_lineage_hash="d" * 64,
        rider_identity_id=rider.identity_id,
        idempotency_key_hash="c" * 64,
        confirmed_at=datetime.now(UTC),
    )
    ride = SimpleNamespace(request_id=confirmation.ride_request_id)
    application = BookingApplication(
        FakeComposition(FakeBookingRepository(item, confirmation)),
        SimpleNamespace(),
        SimpleNamespace(),
        FakeRideRequests(ride),
        uuid4(),
        consent=consent_registry(item),
    )
    recovered = application.recover_confirmation(
        subject=rider, client_request_id=uuid4()
    )
    assert recovered == (confirmation, ride)

    stranger = rider.model_copy(update={"identity_id": uuid4()})
    with pytest.raises(BookingConflict, match="booking_confirmation_not_found"):
        application.recover_confirmation(subject=stranger, client_request_id=uuid4())

    driver = rider.model_copy(
        update={"identity_type": IdentityType.DRIVER, "actor_type": ActorType.DRIVER}
    )
    with pytest.raises(BookingConflict, match="authentication_required"):
        application.recover_confirmation(subject=driver, client_request_id=uuid4())


def test_persisted_booking_retries_same_dispatch_handoff_after_provider_timeout():
    booking_session = "s" * 32
    item = preview().model_copy(
        update={
            "booking_session_hash": hashlib.sha256(booking_session.encode()).hexdigest()
        }
    )
    rider = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    key = "booking-dispatch-retry"
    client_request_id = uuid4()
    consent_policy_version = "booking.consent.v1"
    confirmation = BookingConfirmation(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        ride_request_id=uuid4(),
        rider_identity_id=rider.identity_id,
        idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
        confirmed_at=datetime.now(UTC),
    )
    ride = SimpleNamespace(
        request_id=confirmation.ride_request_id,
        rider_identity_id=rider.identity_id,
        client_request_id=client_request_id,
        consent_policy_version=consent_policy_version,
    )
    dispatch = FlakyDispatch()
    application = BookingApplication(
        FakeComposition(FakeBookingRepository(item, confirmation)),
        SimpleNamespace(),
        SimpleNamespace(),
        FakeRideRequests(ride),
        uuid4(),
        dispatch,
        consent=consent_registry(item),
    )
    command = ConfirmBookingCommand(
        evidence_id=item.evidence_id,
        evidence_hash=item.evidence_hash,
        quote_id=item.quote.quote_id,
        booking_session=booking_session,
        client_request_id=client_request_id,
        idempotency_key=key,
        consent_policy_version=consent_policy_version,
        consent_document_hash=item.consent.content_hash,
        consent_acknowledged=True,
    )
    with pytest.raises(BookingConflict, match="temporarily_unavailable"):
        application.confirm(command, subject=rider, at=datetime.now(UTC))
    stored, returned = application.confirm(command, subject=rider, at=datetime.now(UTC))
    assert stored == confirmation and returned is ride
    assert dispatch.calls == 2
