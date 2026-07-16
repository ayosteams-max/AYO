from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.persistence.tables import canonical_ride_requests, ride_request_outbox
from BACKEND.ride_request.application import (
    CreateRideRequestCommand,
    RideRequestAccessDenied,
    RideRequestApplication,
)
from BACKEND.ride_request.models import (
    Coordinate,
    DestinationDefinition,
    LocationSource,
    PickupDefinition,
    RideRequestState,
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


def setup_rider(composition):
    identity = Identity(
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
        policy_version="zone.policy.v1",
    )
    with composition.unit_of_work() as unit:
        rider = unit.identities.create(identity)
        unit.ride_requests.add_zone(zone)
    subject = AuthorizationSubject(
        identity_id=rider.identity_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    return subject, zone


def command(key="create-001", *, note="private rider note"):
    return CreateRideRequestCommand(
        client_request_id=uuid4(),
        idempotency_key=key,
        pickup=PickupDefinition(
            coordinate=Coordinate(latitude=9.0, longitude=38.7),
            source=LocationSource.RIDER_SELECTED,
            observed_at=NOW,
            accuracy_metres=20,
            note=note,
            map_confidence_bps=8000,
            policy_version="pickup.v1",
        ),
        destination=DestinationDefinition(
            coordinate=Coordinate(latitude=9.02, longitude=38.72),
            source=LocationSource.RIDER_SELECTED,
            observed_at=NOW,
            note="destination private note",
        ),
        consent_policy_version="consent.v1",
    )


def test_create_replay_cancel_ownership_and_safe_outbox(postgres_composition) -> None:
    subject, _ = setup_rider(postgres_composition)
    app = RideRequestApplication(postgres_composition, POLICY)
    cmd = command()
    created = app.create(subject=subject, command=cmd, at=NOW)
    assert created.state is RideRequestState.READY_FOR_DISPATCH
    assert (
        app.create(subject=subject, command=cmd, at=NOW).request_id
        == created.request_id
    )
    other, _ = setup_rider(postgres_composition)
    with pytest.raises(RideRequestAccessDenied, match="resource_access_denied"):
        app.get_owned(subject=other, request_id=created.request_id)
    cancelled = app.cancel(
        subject=subject,
        request_id=created.request_id,
        reason_code="rider.changed_plan",
        expected_version=created.version,
        idempotency_key="cancel-001",
        at=NOW,
    )
    assert cancelled.state is RideRequestState.CANCELLED
    assert (
        app.cancel(
            subject=subject,
            request_id=created.request_id,
            reason_code="rider.changed_plan",
            expected_version=created.version,
            idempotency_key="cancel-001",
            at=NOW,
        ).request_id
        == created.request_id
    )
    with postgres_composition.unit_of_work() as unit:
        payloads = (
            unit.connection.execute(select(ride_request_outbox.c.safe_payload))
            .scalars()
            .all()
        )
    assert all("note" not in str(payload) for payload in payloads)


def test_changed_payload_replay_and_stale_cancel_are_rejected(
    postgres_composition,
) -> None:
    subject, _ = setup_rider(postgres_composition)
    app = RideRequestApplication(postgres_composition, POLICY)
    cmd = command()
    created = app.create(subject=subject, command=cmd, at=NOW)
    with pytest.raises(ValueError, match="different request"):
        app.create(
            subject=subject,
            command=cmd.model_copy(
                update={
                    "destination": cmd.destination.model_copy(
                        update={"note": "changed"}
                    )
                }
            ),
            at=NOW,
        )
    with pytest.raises(ValueError, match="stale_aggregate_version"):
        app.cancel(
            subject=subject,
            request_id=created.request_id,
            reason_code="rider.changed_plan",
            expected_version=1,
            idempotency_key="cancel-stale",
            at=NOW,
        )


def test_concurrent_duplicate_creation_has_one_request(postgres_composition) -> None:
    subject, _ = setup_rider(postgres_composition)
    app = RideRequestApplication(postgres_composition, POLICY)
    cmd = command("concurrent-001")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            f.result()
            for f in [
                pool.submit(app.create, subject=subject, command=cmd, at=NOW),
                pool.submit(app.create, subject=subject, command=cmd, at=NOW),
            ]
        ]
    assert results[0].request_id == results[1].request_id
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(canonical_ride_requests)
            ).scalar_one()
            == 1
        )


def test_inactive_zone_and_duplicate_active_request_fail_validation(
    postgres_composition,
) -> None:
    subject, _ = setup_rider(postgres_composition)
    app = RideRequestApplication(postgres_composition, POLICY)
    first = app.create(subject=subject, command=command("first-001"), at=NOW)
    assert first.state is RideRequestState.READY_FOR_DISPATCH
    second = app.create(subject=subject, command=command("second-001"), at=NOW)
    assert second.state is RideRequestState.VALIDATION_FAILED


def test_non_rider_cannot_create(postgres_composition) -> None:
    identity = Identity(
        identity_type=IdentityType.DRIVER,
        status=AccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    with postgres_composition.unit_of_work() as unit:
        driver = unit.identities.create(identity)
    subject = AuthorizationSubject(
        identity_id=driver.identity_id,
        identity_type=IdentityType.DRIVER,
        actor_type=ActorType.DRIVER,
    )
    with pytest.raises(RideRequestAccessDenied, match="rider_authentication_required"):
        RideRequestApplication(postgres_composition, POLICY).create(
            subject=subject, command=command(), at=NOW
        )


def test_outbox_and_state_roll_back_atomically(postgres_composition) -> None:
    event_id = uuid4()
    with (
        pytest.raises(RuntimeError, match="rollback"),
        postgres_composition.unit_of_work() as unit,
    ):
        unit.connection.execute(
            insert(ride_request_outbox).values(
                event_id=event_id,
                event_type="ride_request.test",
                aggregate_id=uuid4(),
                aggregate_version=1,
                safe_payload={},
                created_at=NOW,
                attempt_count=0,
            )
        )
        raise RuntimeError("rollback")
    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(ride_request_outbox.c.event_id).where(
                    ride_request_outbox.c.event_id == event_id
                )
            ).scalar_one_or_none()
            is None
        )
