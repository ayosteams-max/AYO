from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy import update as sql_update

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.booking.application import (
    BookingApplication,
    ConfirmBookingCommand,
    route_preview_evidence_hash,
)
from BACKEND.booking.consent import ImmutableBookingConsentRegistry
from BACKEND.booking.models import (
    BookingConfirmation,
    BookingConflict,
    BookingConsentMetadata,
    PlaceCandidate,
    ProviderRouteEvidence,
    RoutePreview,
    TollEvidenceState,
    TrafficEvidenceState,
)
from BACKEND.dispatch.handoff import EligibleDriverInput, HandoffState
from BACKEND.dispatch.handoff_service import ImmediateHandoffService
from BACKEND.driver_trust.models import (
    AuthorizationStatus,
    DriverVehicleAuthorization,
    EligibilityDecision,
    EligibilityStatus,
    Vehicle,
    VehicleApprovalStatus,
)
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.localization.models import LanguagePackManifest, TextDirection
from BACKEND.localization.service import LocalizationService
from BACKEND.persistence.handoff_dispatch_repository import HandoffConflict
from BACKEND.persistence.tables import (
    booking_confirmations,
    booking_route_evidence,
    canonical_ride_requests,
    dispatch_outbox,
    fare_estimate_acceptances,
    fare_estimates,
    immediate_dispatch_assignments,
    immediate_dispatch_outbox,
    pricing_outbox,
    ride_request_outbox,
)
from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.booking import BookingPricingApplication
from BACKEND.pricing.models import (
    DataQuality,
    PricingPolicy,
    RouteMetrics,
)
from BACKEND.ride_request.application import (
    CreateRideRequestCommand,
    RideRequestApplication,
)
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    ServiceZone,
    ValidationPolicy,
)


class CountingBookingDispatch:
    def __init__(self) -> None:
        self.calls = 0

    def start(self, **kwargs) -> None:
        del kwargs
        self.calls += 1


class ConfirmationOnlyRoutes:
    def search_places(
        self, *, query: str, locale: str, limit: int, at: datetime
    ) -> tuple[PlaceCandidate, ...]:
        del query, locale, limit, at
        raise AssertionError("confirmation must not search for places")

    def route(
        self, *, origin: Coordinate, destination: Coordinate, at: datetime
    ) -> ProviderRouteEvidence:
        del origin, destination, at
        raise AssertionError("confirmation must not request route intelligence")


def consent_manifest(
    *, version: str, content_hash: str, start: datetime, end: datetime
) -> BookingConsentMetadata:
    return BookingConsentMetadata(
        required_version=version,
        document_id="booking.immediate-standard.synthetic",
        content_hash=content_hash,
        effective_from=start,
        effective_until=end,
        acknowledgment_required=True,
    )


def consent_booking_scenario(composition):
    rider = Identity(
        identity_type=IdentityType.RIDER,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    zone = ServiceZone(
        code=f"consent.zone.{uuid4().hex}",
        version="zone.consent.v1",
        min_latitude=8.5,
        max_latitude=9.5,
        min_longitude=38.2,
        max_longitude=39.2,
        supported_service_types=frozenset({"immediate_standard"}),
        active_from=NOW - timedelta(days=1),
        policy_version="zone.consent.v1",
    )
    with composition.unit_of_work() as unit:
        rider = unit.identities.create(rider)
        unit.ride_requests.add_zone(zone)
        staff = tuple(
            unit.identities.create(
                Identity(
                    identity_type=IdentityType.STAFF,
                    status=AccountStatus.ACTIVE,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            for _ in range(3)
        )
    subject = AuthorizationSubject(
        identity_id=rider.identity_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    operators = tuple(
        AuthorizationSubject(
            identity_id=item.identity_id,
            identity_type=IdentityType.STAFF,
            actor_type=ActorType.STAFF,
        )
        for item in staff
    )
    pricing = PricingApplication(composition)
    policy = pricing.create_policy(
        operators[0],
        PricingPolicy(
            policy_version=f"pricing.consent.{uuid4().hex[:12]}",
            service_zone_id=zone.zone_id,
            service_type="immediate_standard",
            currency="ETB",
            base_fare_minor=100,
            distance_rate_per_km_minor=10,
            time_rate_per_minute_minor=5,
            minimum_fare_minor=100,
            commission_basis_points=0,
            rounding_increment_minor=1,
            effective_from=NOW - timedelta(days=1),
            made_by_identity_id=operators[0].identity_id,
            created_at=NOW,
        ),
    )
    policy = pricing.approve_policy(operators[1], policy.policy_id, at=NOW)
    policy = pricing.publish_policy(operators[2], policy.policy_id, at=NOW)
    pickup = PickupDefinition(
        coordinate=Coordinate(latitude=9, longitude=38.7),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
        accuracy_metres=10,
        policy_version="pickup.synthetic.v1",
    )
    destination = DestinationDefinition(
        coordinate=Coordinate(latitude=9.02, longitude=38.72),
        source=LocationSource.RIDER_SELECTED,
        observed_at=NOW,
    )
    metrics = RouteMetrics(
        distance_meters=2000,
        duration_seconds=600,
        observed_at=NOW,
        provider_id="approved_synthetic",
        provider_version="route.synthetic.v1",
        distance_source="approved_synthetic",
        duration_source="approved_synthetic",
        provenance_reference=f"consent-{uuid4()}",
        data_quality=DataQuality.APPROVED_SYNTHETIC,
    )
    route = ProviderRouteEvidence(
        metrics=metrics,
        geometry=((9, 38.7), (9.02, 38.72)),
        origin_accuracy_metres=10,
        destination_accuracy_metres=10,
        map_confidence_bps=9000,
        traffic_state=TrafficEvidenceState.NOT_REQUESTED,
        toll_state=TollEvidenceState.UNKNOWN,
        attribution="Approved synthetic test evidence",
    )
    quote = BookingPricingApplication(composition).quote(
        policy_id=policy.policy_id,
        service_zone_id=zone.zone_id,
        metrics=metrics,
        at=NOW,
    )
    consent = consent_manifest(
        version="booking.consent.synthetic.v1",
        content_hash="e" * 64,
        start=NOW - timedelta(days=1),
        end=NOW + timedelta(days=1),
    )
    session = "s" * 32
    import hashlib

    evidence_id = uuid4()
    evidence_hash = route_preview_evidence_hash(
        evidence_id=evidence_id,
        booking_session_hash=hashlib.sha256(session.encode()).hexdigest(),
        pickup=pickup,
        destination=destination,
        route=route,
        quote=quote,
        consent=consent,
        service_zone_version=zone.version,
    )
    preview = RoutePreview(
        evidence_id=evidence_id,
        booking_session_hash=hashlib.sha256(session.encode()).hexdigest(),
        rider_identity_id=rider.identity_id,
        pickup=pickup,
        destination=destination,
        service_zone_id=zone.zone_id,
        service_zone_version=zone.version,
        service_type="immediate_standard",
        route=route,
        quote=quote,
        consent=consent,
        evidence_hash=evidence_hash,
        created_at=NOW,
        expires_at=quote.expires_at,
    )
    with composition.unit_of_work() as unit:
        preview = unit.booking.add_preview(preview)
    dispatch = CountingBookingDispatch()
    application = BookingApplication(
        composition,
        ConfirmationOnlyRoutes(),
        BookingPricingApplication(composition),
        RideRequestApplication(composition, POLICY),
        policy.policy_id,
        dispatch,
        consent=ImmutableBookingConsentRegistry((consent,)),
    )
    command = ConfirmBookingCommand(
        evidence_id=preview.evidence_id,
        evidence_hash=preview.evidence_hash,
        quote_id=preview.quote.quote_id,
        booking_session=session,
        client_request_id=uuid4(),
        idempotency_key=f"consent-confirm-{uuid4().hex}",
        consent_policy_version=consent.required_version,
        consent_document_hash=consent.content_hash,
        consent_acknowledged=True,
    )
    return application, command, subject, preview, consent, dispatch


pytestmark = [pytest.mark.integration, pytest.mark.authorization]
NOW = datetime(2026, 7, 16, tzinfo=UTC)
POLICY = ValidationPolicy(
    version="ride.validation.v1",
    maximum_accuracy_metres=100,
    maximum_observation_age_seconds=300,
    minimum_separation_metres=50,
    request_ttl_seconds=900,
    effective_from=NOW - timedelta(days=1),
)


def ready_request(composition):
    rider = Identity(
        identity_type=IdentityType.RIDER,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    zone = ServiceZone(
        code=f"zone.{uuid4().hex}",
        version="zone.v1",
        min_latitude=8.5,
        max_latitude=9.5,
        min_longitude=38.2,
        max_longitude=39.2,
        supported_service_types=frozenset({"immediate_standard"}),
        active_from=NOW - timedelta(days=1),
        policy_version="zone.v1",
    )
    with composition.unit_of_work() as unit:
        rider = unit.identities.create(rider)
        unit.ride_requests.add_zone(zone)
    subject = AuthorizationSubject(
        identity_id=rider.identity_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    cmd = CreateRideRequestCommand(
        client_request_id=uuid4(),
        idempotency_key=f"ready-request-{rider.identity_id}",
        pickup=PickupDefinition(
            coordinate=Coordinate(latitude=9, longitude=38.7),
            source=LocationSource.RIDER_SELECTED,
            observed_at=NOW,
            accuracy_metres=10,
            note="never dispatch this note",
            policy_version="pickup.v1",
        ),
        destination=DestinationDefinition(
            coordinate=Coordinate(latitude=9.02, longitude=38.72),
            source=LocationSource.RIDER_SELECTED,
            observed_at=NOW,
            note="private destination",
        ),
        consent_policy_version="consent.v1",
    )
    request = RideRequestApplication(composition, POLICY).create(
        subject=subject, command=cmd, at=NOW
    )
    with composition.unit_of_work() as unit:
        authoritative_zone = unit.ride_requests.find_zone(
            latitude=9, longitude=38.7, at=NOW
        )
    assert authoritative_zone is not None
    assert authoritative_zone.zone_id == request.service_zone_id
    makers = []
    with composition.unit_of_work() as unit:
        for _ in range(3):
            makers.append(
                unit.identities.create(
                    Identity(
                        identity_type=IdentityType.STAFF,
                        status=AccountStatus.ACTIVE,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
            )
    operators = [
        AuthorizationSubject(
            identity_id=item.identity_id,
            identity_type=IdentityType.STAFF,
            actor_type=ActorType.STAFF,
        )
        for item in makers
    ]
    pricing = PricingApplication(composition)
    policy = pricing.create_policy(
        operators[0],
        PricingPolicy(
            policy_version=f"pricing.synthetic.{request.request_id.hex[:12]}",
            service_zone_id=request.service_zone_id,
            service_type="immediate_standard",
            currency="ETB",
            base_fare_minor=100,
            distance_rate_per_km_minor=10,
            time_rate_per_minute_minor=5,
            minimum_fare_minor=100,
            commission_basis_points=0,
            rounding_increment_minor=1,
            effective_from=NOW - timedelta(days=1),
            made_by_identity_id=operators[0].identity_id,
            created_at=NOW,
        ),
    )
    policy = pricing.approve_policy(operators[1], policy.policy_id, at=NOW)
    policy = pricing.publish_policy(operators[2], policy.policy_id, at=NOW)
    metrics = RouteMetrics(
        distance_meters=2000,
        duration_seconds=600,
        observed_at=NOW,
        provider_id="approved_synthetic",
        provider_version="route.synthetic.v1",
        distance_source="approved_synthetic",
        duration_source="approved_synthetic",
        provenance_reference=f"route-{request.request_id}",
        data_quality=DataQuality.APPROVED_SYNTHETIC,
    )
    estimate = pricing.estimate(
        subject,
        ride_request_id=request.request_id,
        policy_id=policy.policy_id,
        metrics=metrics,
        idempotency_key=f"estimate-{request.request_id}",
        correlation_id=request.request_id,
        causation_id=request.request_id,
        at=NOW,
    )
    acceptance = pricing.accept(
        subject,
        estimate.estimate_id,
        idempotency_key=f"acceptance-{request.request_id}",
        at=NOW,
    )
    evidence_id = uuid4()
    lineage_payload = ":".join(
        (
            str(request.request_id),
            str(estimate.estimate_id),
            str(acceptance.acceptance_id),
            str(estimate.policy_id),
            estimate.policy_version,
            str(acceptance.accepted_amount_minor),
            acceptance.currency,
        )
    )
    import hashlib

    with composition.unit_of_work() as unit:
        unit.connection.execute(
            insert(booking_route_evidence).values(
                evidence_id=evidence_id,
                booking_session_hash="a" * 64,
                rider_identity_id=rider.identity_id,
                pickup_payload={},
                destination_payload={},
                service_zone_id=request.service_zone_id,
                service_zone_version=authoritative_zone.version,
                service_type="immediate_standard",
                route_payload={},
                quote_payload={},
                evidence_hash="b" * 64,
                created_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
            )
        )
        unit.booking.add_confirmation(
            BookingConfirmation(
                evidence_id=evidence_id,
                evidence_hash="b" * 64,
                quote_id=uuid4(),
                ride_request_id=request.request_id,
                fare_estimate_id=estimate.estimate_id,
                estimate_acceptance_id=acceptance.acceptance_id,
                pricing_lineage_hash=hashlib.sha256(
                    lineage_payload.encode()
                ).hexdigest(),
                rider_identity_id=rider.identity_id,
                idempotency_key_hash="c" * 64,
                confirmed_at=NOW,
            )
        )
    return request, subject


def eligible_driver(composition, cost=20):
    identity = Identity(
        identity_type=IdentityType.DRIVER,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    vehicle = Vehicle(
        canonical_reference_hash=uuid4().bytes + uuid4().bytes,
        category="vehicle.standard",
        approval_status=VehicleApprovalStatus.APPROVED,
        policy_version="identity.v1",
        created_at=NOW,
        updated_at=NOW,
    )
    with composition.unit_of_work() as unit:
        identity = unit.identities.create(identity)
        unit.driver_trust.add_vehicle(vehicle)
        unit.driver_trust.add_vehicle_authorization(
            DriverVehicleAuthorization(
                driver_identity_id=identity.identity_id,
                vehicle_id=vehicle.vehicle_id,
                status=AuthorizationStatus.AUTHORIZED,
                policy_version="identity.v1",
                effective_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=2),
            )
        )
        unit.driver_trust.append_eligibility(
            EligibilityDecision(
                driver_identity_id=identity.identity_id,
                vehicle_id=vehicle.vehicle_id,
                policy_version="identity.v1",
                status=EligibilityStatus.ELIGIBLE,
                reason_codes=("all_requirements_current",),
                missing_evidence=(),
                expires_at=NOW + timedelta(days=1),
                recomputed_at=NOW,
                audit_reference=uuid4(),
            )
        )
    return EligibleDriverInput(
        driver_id=identity.identity_id,
        vehicle_id=vehicle.vehicle_id,
        authorized_vehicle_id=vehicle.vehicle_id,
        account_active=True,
        eligibility_status="eligible",
        eligibility_expires_at=NOW + timedelta(days=1),
        vehicle_approved=True,
        supported_services=frozenset({"immediate_standard"}),
        availability="available",
        availability_observed_at=NOW,
        pickup_cost_seconds=cost,
        eligibility_policy_version="identity.v1",
    )


def test_booking_confirmation_recovery_is_client_request_and_rider_scoped(
    postgres_composition,
) -> None:
    request, subject = ready_request(postgres_composition)
    with postgres_composition.unit_of_work() as unit:
        recovered = unit.booking.get_confirmation_for_client_request(
            rider_identity_id=subject.identity_id,
            client_request_id=request.client_request_id,
        )
        cross_rider = unit.booking.get_confirmation_for_client_request(
            rider_identity_id=uuid4(),
            client_request_id=request.client_request_id,
        )
    assert recovered is not None
    assert recovered.ride_request_id == request.request_id
    assert recovered.rider_identity_id == subject.identity_id
    assert recovered.fare_estimate_id is not None
    assert recovered.estimate_acceptance_id is not None
    assert recovered.pricing_lineage_hash is not None
    assert cross_rider is None


def test_booking_confirmation_idempotency_hash_lookup_is_scoped_and_restart_safe(
    postgres_composition,
) -> None:
    request, subject = ready_request(postgres_composition)

    def reload_confirmation():
        with postgres_composition.unit_of_work() as unit:
            return unit.booking.get_confirmation_for_idempotency_key_hash(
                rider_identity_id=subject.identity_id,
                idempotency_key_hash="c" * 64,
            )

    first = reload_confirmation()
    second = reload_confirmation()
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = tuple(executor.map(lambda _: reload_confirmation(), range(8)))
    with postgres_composition.unit_of_work() as unit:
        wrong_rider = unit.booking.get_confirmation_for_idempotency_key_hash(
            rider_identity_id=uuid4(),
            idempotency_key_hash="c" * 64,
        )
        wrong_hash = unit.booking.get_confirmation_for_idempotency_key_hash(
            rider_identity_id=subject.identity_id,
            idempotency_key_hash="d" * 64,
        )

    assert first is not None
    assert first.ride_request_id == request.request_id
    assert second == first
    assert all(item == first for item in concurrent)
    assert wrong_rider is None
    assert wrong_hash is None


def test_booking_consent_binding_reconstructs_across_units_of_work(
    postgres_composition,
) -> None:
    _, _, _, preview, consent, _ = consent_booking_scenario(postgres_composition)

    def reload_preview():
        with postgres_composition.unit_of_work() as unit:
            return unit.booking.get_preview(preview.evidence_id)

    reloaded = reload_preview()
    with ThreadPoolExecutor(max_workers=4) as executor:
        concurrent = tuple(executor.map(lambda _: reload_preview(), range(8)))
    assert reloaded == preview
    assert reloaded is not None and reloaded.consent == consent
    assert all(item == preview for item in concurrent)


def test_booking_consent_legacy_quote_payload_reconstructs_without_guessing(
    postgres_composition,
) -> None:
    _, command, subject, preview, consent, dispatch = consent_booking_scenario(
        postgres_composition
    )
    del consent
    before = booking_side_effect_counts(postgres_composition)
    with postgres_composition.unit_of_work() as unit:
        unit.connection.execute(
            sql_update(booking_route_evidence)
            .where(booking_route_evidence.c.evidence_id == preview.evidence_id)
            .values(quote_payload=preview.quote.model_dump(mode="json"))
        )

    after_legacy_write = booking_side_effect_counts(postgres_composition)
    with postgres_composition.unit_of_work() as unit:
        reconstructed = unit.booking.get_preview(preview.evidence_id)

    assert reconstructed is not None
    assert reconstructed.quote == preview.quote
    assert reconstructed.consent is None
    assert booking_side_effect_counts(postgres_composition) == after_legacy_write
    assert after_legacy_write == before

    assert preview.consent is not None
    application = BookingApplication(
        postgres_composition,
        ConfirmationOnlyRoutes(),
        BookingPricingApplication(postgres_composition),
        RideRequestApplication(postgres_composition, POLICY),
        preview.quote.policy_id,
        dispatch,
        consent=ImmutableBookingConsentRegistry((preview.consent,)),
    )
    with pytest.raises(BookingConflict) as raised:
        application.confirm(command, subject=subject, at=NOW)
    assert str(raised.value) == "consent_policy_changed"
    assert booking_side_effect_counts(postgres_composition) == before
    assert dispatch.calls == 0


def booking_side_effect_counts(composition) -> dict[str, int]:
    tables = {
        "rides": canonical_ride_requests,
        "confirmations": booking_confirmations,
        "estimates": fare_estimates,
        "acceptances": fare_estimate_acceptances,
        "ride_outbox": ride_request_outbox,
        "pricing_outbox": pricing_outbox,
        "dispatch_outbox": dispatch_outbox,
        "immediate_dispatch_outbox": immediate_dispatch_outbox,
    }
    with composition.unit_of_work() as unit:
        return {
            name: unit.connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
            for name, table in tables.items()
        }


def test_booking_consent_confirmation_persists_authority_and_replays_canonically(
    postgres_composition,
) -> None:
    application, command, subject, preview, consent, dispatch = (
        consent_booking_scenario(postgres_composition)
    )
    confirmation, ride = application.confirm(command, subject=subject, at=NOW)
    after_first = booking_side_effect_counts(postgres_composition)

    reconstructed = BookingApplication(
        postgres_composition,
        ConfirmationOnlyRoutes(),
        BookingPricingApplication(postgres_composition),
        RideRequestApplication(postgres_composition, POLICY),
        preview.quote.policy_id,
        dispatch,
        consent=ImmutableBookingConsentRegistry((consent,)),
    )
    replayed = reconstructed.confirm(command, subject=subject, at=NOW)
    recovered = reconstructed.recover_confirmation(
        subject=subject, client_request_id=command.client_request_id
    )

    def concurrent_replay(_: int):
        concurrent_application = BookingApplication(
            postgres_composition,
            ConfirmationOnlyRoutes(),
            BookingPricingApplication(postgres_composition),
            RideRequestApplication(postgres_composition, POLICY),
            preview.quote.policy_id,
            dispatch,
            consent=ImmutableBookingConsentRegistry((consent,)),
        )
        return concurrent_application.confirm(command, subject=subject, at=NOW)

    with ThreadPoolExecutor(max_workers=3) as executor:
        concurrent = tuple(executor.map(concurrent_replay, range(3)))
    with postgres_composition.unit_of_work() as unit:
        stored_preview = unit.booking.get_preview(preview.evidence_id)
        stored_confirmation = unit.booking.get_confirmation_for_evidence(
            preview.evidence_id
        )
        stored_ride = unit.ride_requests.get(ride.request_id)
    assert stored_preview is not None and stored_preview.consent == consent
    assert stored_confirmation == confirmation
    assert stored_ride is not None
    assert stored_ride.consent_policy_version == consent.required_version
    assert replayed == (confirmation, ride)
    assert recovered == (confirmation, ride)
    assert all(item == (confirmation, ride) for item in concurrent)
    assert booking_side_effect_counts(postgres_composition) == after_first

    for update in (
        {"consent_policy_version": "booking.consent.synthetic.v2"},
        {"consent_document_hash": "f" * 64},
    ):
        with pytest.raises(BookingConflict) as raised:
            reconstructed.confirm(
                command.model_copy(update=update), subject=subject, at=NOW
            )
        assert str(raised.value) == "idempotency_conflict"
        assert "consent" not in str(raised.value)
    assert booking_side_effect_counts(postgres_composition) == after_first
    assert dispatch.calls == 5


def test_booking_consent_rotation_and_legacy_reject_without_persisted_effects(
    postgres_composition,
) -> None:
    application, command, subject, preview, consent_v1, dispatch = (
        consent_booking_scenario(postgres_composition)
    )
    del application
    rotation_time = NOW + timedelta(seconds=1)
    v1 = consent_v1.model_copy(update={"effective_until": rotation_time})
    v2 = consent_manifest(
        version="booking.consent.synthetic.v2",
        content_hash="f" * 64,
        start=rotation_time,
        end=NOW + timedelta(days=1),
    )
    reconstructed = BookingApplication(
        postgres_composition,
        ConfirmationOnlyRoutes(),
        BookingPricingApplication(postgres_composition),
        RideRequestApplication(postgres_composition, POLICY),
        preview.quote.policy_id,
        dispatch,
        consent=ImmutableBookingConsentRegistry((v1, v2)),
    )
    before = booking_side_effect_counts(postgres_composition)
    with pytest.raises(BookingConflict) as raised:
        reconstructed.confirm(command, subject=subject, at=rotation_time)
    assert str(raised.value) == "consent_policy_changed"
    assert booking_side_effect_counts(postgres_composition) == before

    deliberate_v2 = preview.model_copy(
        update={
            "evidence_id": uuid4(),
            "consent": v2,
            "evidence_hash": "b" * 64,
            "created_at": rotation_time,
        }
    )
    with postgres_composition.unit_of_work() as unit:
        assert unit.booking.add_preview(deliberate_v2).consent == v2
        assert unit.booking.get_preview(preview.evidence_id) == preview

    legacy = preview.model_copy(
        update={"evidence_id": uuid4(), "consent": None, "evidence_hash": "c" * 64}
    )
    with postgres_composition.unit_of_work() as unit:
        unit.booking.add_preview(legacy)
    legacy_command = command.model_copy(
        update={
            "evidence_id": legacy.evidence_id,
            "evidence_hash": legacy.evidence_hash,
            "quote_id": legacy.quote.quote_id,
            "client_request_id": uuid4(),
            "idempotency_key": f"legacy-consent-{uuid4().hex}",
        }
    )
    before_legacy = booking_side_effect_counts(postgres_composition)
    with pytest.raises(BookingConflict) as raised:
        reconstructed.confirm(legacy_command, subject=subject, at=NOW)
    assert str(raised.value) == "consent_policy_changed"
    assert booking_side_effect_counts(postgres_composition) == before_legacy
    with postgres_composition.unit_of_work() as unit:
        assert unit.booking.get_preview(legacy.evidence_id) == legacy
        assert unit.booking.get_confirmation_for_evidence(legacy.evidence_id) is None
    assert dispatch.calls == 0


def test_booking_consent_concurrent_stale_confirmation_cannot_bypass_rotation(
    postgres_composition,
) -> None:
    _, command, subject, preview, consent_v1, dispatch = consent_booking_scenario(
        postgres_composition
    )
    rotation_time = NOW + timedelta(seconds=1)
    v1 = consent_v1.model_copy(update={"effective_until": rotation_time})
    v2 = consent_manifest(
        version="booking.consent.synthetic.v2",
        content_hash="f" * 64,
        start=rotation_time,
        end=NOW + timedelta(days=1),
    )

    def reject_stale(_: int) -> str:
        application = BookingApplication(
            postgres_composition,
            ConfirmationOnlyRoutes(),
            BookingPricingApplication(postgres_composition),
            RideRequestApplication(postgres_composition, POLICY),
            preview.quote.policy_id,
            dispatch,
            consent=ImmutableBookingConsentRegistry((v1, v2)),
        )
        with pytest.raises(BookingConflict) as raised:
            application.confirm(command, subject=subject, at=rotation_time)
        return str(raised.value)

    before = booking_side_effect_counts(postgres_composition)
    with ThreadPoolExecutor(max_workers=3) as executor:
        outcomes = tuple(executor.map(reject_stale, range(3)))
    assert outcomes == ("consent_policy_changed",) * 3
    assert booking_side_effect_counts(postgres_composition) == before
    assert dispatch.calls == 0


def test_booking_consent_concurrent_first_confirmation_has_one_canonical_result(
    postgres_composition,
) -> None:
    _, command, subject, preview, consent, _ = consent_booking_scenario(
        postgres_composition
    )
    barrier = Barrier(3)

    def confirm_once(index: int):
        candidate = command
        if index == 2:
            candidate = command.model_copy(update={"consent_document_hash": "f" * 64})
        application = BookingApplication(
            postgres_composition,
            ConfirmationOnlyRoutes(),
            BookingPricingApplication(postgres_composition),
            RideRequestApplication(postgres_composition, POLICY),
            preview.quote.policy_id,
            consent=ImmutableBookingConsentRegistry((consent,)),
        )
        barrier.wait()
        try:
            return application.confirm(candidate, subject=subject, at=NOW)
        except BookingConflict as error:
            return str(error)

    before = booking_side_effect_counts(postgres_composition)
    with ThreadPoolExecutor(max_workers=3) as executor:
        outcomes = tuple(executor.map(confirm_once, range(3)))
    successes = tuple(item for item in outcomes if isinstance(item, tuple))
    failures = tuple(item for item in outcomes if isinstance(item, str))
    assert successes
    canonical_confirmation, canonical_ride = successes[0]
    assert all(item == (canonical_confirmation, canonical_ride) for item in successes)
    assert failures and set(failures) <= {
        "consent_policy_changed",
        "idempotency_conflict",
    }
    after = booking_side_effect_counts(postgres_composition)
    assert after["rides"] - before["rides"] == 1
    assert after["confirmations"] - before["confirmations"] == 1
    assert after["estimates"] - before["estimates"] == 1
    assert after["acceptances"] - before["acceptances"] == 1
    assert after["ride_outbox"] - before["ride_outbox"] == 4
    assert after["pricing_outbox"] - before["pricing_outbox"] == 2
    assert after["dispatch_outbox"] == before["dispatch_outbox"]
    assert after["immediate_dispatch_outbox"] == before["immediate_dispatch_outbox"]
    with postgres_composition.unit_of_work() as unit:
        stored_preview = unit.booking.get_preview(preview.evidence_id)
        stored_confirmation = unit.booking.get_confirmation_for_evidence(
            preview.evidence_id
        )
        stored_ride = unit.ride_requests.get(canonical_ride.request_id)
    assert stored_preview is not None and stored_preview.consent == consent
    assert stored_confirmation == canonical_confirmation
    assert stored_ride is not None
    assert stored_ride.consent_policy_version == consent.required_version


def test_handoff_minimizes_data_and_fastest_authoritative_driver_wins(
    postgres_composition,
) -> None:
    request, _ = ready_request(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1"
    )
    actor = uuid4()
    handoff = service.receive(
        ride_request_id=request.request_id,
        service_actor_id=actor,
        idempotency_key="handoff-idempotency-001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    assert (
        service.receive(
            ride_request_id=request.request_id,
            service_actor_id=actor,
            idempotency_key="handoff-idempotency-001",
            correlation_id=handoff.correlation_id,
            causation_id=handoff.causation_id,
            at=NOW,
        ).handoff_id
        == handoff.handoff_id
    )
    slow = eligible_driver(postgres_composition, 80)
    fast = eligible_driver(postgres_composition, 15)
    forged = fast.model_copy(update={"driver_id": uuid4(), "pickup_cost_seconds": 1})
    offer = service.offer_next(
        handoff.handoff_id, observations=[slow, forged, fast], at=NOW
    )
    assert offer is not None and offer.driver_id == fast.driver_id
    with postgres_composition.unit_of_work() as unit:
        payloads = (
            unit.connection.execute(select(immediate_dispatch_outbox.c.safe_payload))
            .scalars()
            .all()
        )
    assert all("note" not in str(x) and "destination" not in str(x) for x in payloads)


def test_expired_accepted_pricing_cannot_enter_dispatch(postgres_composition) -> None:
    request, _ = ready_request(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1"
    )

    with pytest.raises(HandoffConflict, match="dispatch.accepted_pricing_required"):
        service.receive(
            ride_request_id=request.request_id,
            service_actor_id=uuid4(),
            idempotency_key="handoff-expired-pricing-001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW + timedelta(minutes=11),
        )


def test_duplicate_acceptance_returns_one_assignment_and_changed_replay_fails(
    postgres_composition,
) -> None:
    request, _ = ready_request(postgres_composition)
    driver = eligible_driver(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1"
    )
    handoff = service.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key="handoff-idempotency-002",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = service.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            f.result()
            for f in [
                pool.submit(
                    service.respond,
                    offer_id=offer.offer_id,
                    driver_id=driver.driver_id,
                    accept=True,
                    expected_version=1,
                    idempotency_key="offer-response-001",
                    at=NOW,
                ),
                pool.submit(
                    service.respond,
                    offer_id=offer.offer_id,
                    driver_id=driver.driver_id,
                    accept=True,
                    expected_version=1,
                    idempotency_key="offer-response-001",
                    at=NOW,
                ),
            ]
        ]
    assert results[0] == results[1]
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(immediate_dispatch_assignments)
            ).scalar_one()
            == 1
        )
    with pytest.raises(ValueError, match="different request"):
        service.respond(
            offer_id=offer.offer_id,
            driver_id=driver.driver_id,
            accept=False,
            expected_version=1,
            idempotency_key="offer-response-001",
            at=NOW,
        )


def test_cancellation_wins_before_acceptance_and_unvalidated_handoff_fails(
    postgres_composition,
) -> None:
    request, _ = ready_request(postgres_composition)
    driver = eligible_driver(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1"
    )
    handoff = service.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key="handoff-idempotency-003",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = service.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer
    assert service.cancel_before_assignment(request.request_id, at=NOW)
    with pytest.raises(HandoffConflict):
        service.respond(
            offer_id=offer.offer_id,
            driver_id=driver.driver_id,
            accept=True,
            expected_version=1,
            idempotency_key="offer-response-003",
            at=NOW,
        )
    with pytest.raises(HandoffConflict):
        service.receive(
            ride_request_id=uuid4(),
            service_actor_id=uuid4(),
            idempotency_key="handoff-invalid-0001",
            correlation_id=uuid4(),
            causation_id=uuid4(),
            at=NOW,
        )


def test_cancellation_acceptance_race_has_one_terminal_winner(
    postgres_composition,
) -> None:
    request, _ = ready_request(postgres_composition)
    driver = eligible_driver(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1"
    )
    handoff = service.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key="handoff-race-accept-001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = service.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer is not None

    def accept() -> str:
        try:
            service.respond(
                offer_id=offer.offer_id,
                driver_id=driver.driver_id,
                accept=True,
                expected_version=1,
                idempotency_key="offer-race-accept-001",
                at=NOW,
            )
            return "assigned"
        except HandoffConflict:
            return "lost"

    def cancel() -> str:
        try:
            service.cancel_before_assignment(request.request_id, at=NOW)
            return "cancelled"
        except HandoffConflict:
            return "lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(accept), pool.submit(cancel)]
        outcomes = {future.result() for future in futures}
    with postgres_composition.unit_of_work() as unit:
        final = unit.handoff_dispatch.get_handoff(handoff.handoff_id)
    assert final is not None
    assert final.state in {HandoffState.ASSIGNED, HandoffState.CANCELLED}
    assert "lost" in outcomes


def test_language_preference_is_owned_versioned_and_does_not_mutate_dispatch(
    postgres_composition,
) -> None:
    request, subject = ready_request(postgres_composition)
    service = LocalizationService(postgres_composition)
    first = service.set_own_preference(
        subject=subject,
        preferred_language="ar",
        device_language="en-AU",
        fallback_chain=("en", "am"),
        expected_version=None,
        at=NOW,
    )
    assert first.version == 1
    changed = service.set_own_preference(
        subject=subject,
        preferred_language="fr-ET",
        device_language=None,
        fallback_chain=("en",),
        expected_version=1,
        at=NOW,
    )
    assert changed.version == 2
    preference = service.get_own_preference(subject=subject)
    assert preference is not None
    assert preference.preferred_language == "fr-ET"
    with postgres_composition.unit_of_work() as unit:
        assert unit.ride_requests.get(request.request_id).version == request.version
        unit.localization.add_manifest(
            LanguagePackManifest(
                language_tag="ar",
                pack_version="v1",
                direction=TextDirection.RIGHT_TO_LEFT,
                date_format_profile="cldr.ar",
                number_format_profile="cldr.ar",
                currency_format_profile="cldr.ar",
            )
        )
        assert unit.localization.manifest("ar").direction is TextDirection.RIGHT_TO_LEFT


def test_expired_offer_recovers_to_searching(postgres_composition) -> None:
    request, _ = ready_request(postgres_composition)
    driver = eligible_driver(postgres_composition)
    service = ImmediateHandoffService(
        postgres_composition, policy_version="dispatch.v1", offer_timeout_seconds=5
    )
    handoff = service.receive(
        ride_request_id=request.request_id,
        service_actor_id=uuid4(),
        idempotency_key="handoff-expiry-test-001",
        correlation_id=uuid4(),
        causation_id=uuid4(),
        at=NOW,
    )
    offer = service.offer_next(handoff.handoff_id, observations=[driver], at=NOW)
    assert offer is not None
    service.expire_offer(offer.offer_id, at=NOW + timedelta(seconds=6))
    with postgres_composition.unit_of_work() as unit:
        recovered = unit.handoff_dispatch.get_handoff(handoff.handoff_id)
    assert recovered is not None
    assert recovered.state is HandoffState.SEARCHING
