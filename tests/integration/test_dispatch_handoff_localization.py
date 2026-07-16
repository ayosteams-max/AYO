from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
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
    immediate_dispatch_assignments,
    immediate_dispatch_outbox,
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
        idempotency_key="ready-request-001",
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
    return RideRequestApplication(composition, POLICY).create(
        subject=subject, command=cmd, at=NOW
    ), subject


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
    assert service.get_own_preference(subject=subject).preferred_language == "fr-ET"
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
