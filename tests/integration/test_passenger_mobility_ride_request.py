from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.customer_profile.models import RelationshipState, RelationshipType
from BACKEND.persistence.errors import IdempotencyConflictError
from BACKEND.persistence.tables import (
    audit_events,
    canonical_ride_requests,
    canonical_subjects,
    customer_household_relationships,
    identity_accounts,
    persistence_domain_events,
    persistence_idempotency_records,
    persistence_outbox,
)
from BACKEND.persistence.trace import TraceContext
from BACKEND.ride_request.mobility_application import (
    CreatePassengerMobilityRideRequest,
    PassengerMobilityRideRequestService,
    RideRequestAuthorizationError,
)
from BACKEND.ride_request.models import (
    LuggagePreference,
    MobilityRideRequestState,
    RideIntentPreferences,
    ScheduleIntentType,
)

pytestmark = [pytest.mark.integration, pytest.mark.passenger_mobility]


def trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def account(engine) -> tuple[UUID, UUID]:
    now = datetime.now(UTC)
    subject_id, account_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(canonical_subjects).values(
                subject_id=subject_id,
                subject_kind="human",
                created_at=now,
                version=1,
            )
        )
        connection.execute(
            insert(identity_accounts).values(
                account_id=account_id,
                subject_id=subject_id,
                state="active",
                created_at=now,
                updated_at=now,
                version=1,
                failed_attempt_count=0,
                credential_change_required=False,
            )
        )
    return account_id, subject_id


def command(passenger_subject_id: UUID, **changes):
    now = datetime.now(UTC)
    values = {
        "client_request_id": uuid4(),
        "passenger_subject_id": passenger_subject_id,
        "pickup_reference": "place:addis-bole",
        "destination_reference": "place:addis-piassa",
        "stop_references": ("place:addis-meskel",),
        "schedule_intent": ScheduleIntentType.IMMEDIATE,
        "passenger_count": 2,
        "preferences": RideIntentPreferences(
            accessibility_needs=("mobility.wheelchair",),
            luggage=LuggagePreference.LARGE,
            quiet_ride=True,
            child_seat=True,
            child_seat_count=1,
        ),
        "expires_at": now + timedelta(hours=2),
    }
    values.update(changes)
    return CreatePassengerMobilityRideRequest.model_validate(values)


def test_self_request_lifecycle_idempotency_audit_outbox_restart(postgres_engine):
    service = PassengerMobilityRideRequestService(postgres_engine)
    account_id, subject_id = account(postgres_engine)
    create = command(subject_id)
    created = service.create_draft(
        actor_account_id=account_id,
        command=create,
        idempotency_key="mobility-create-self-0001",
        trace=trace(),
    )
    replay = service.create_draft(
        actor_account_id=account_id,
        command=create,
        idempotency_key="mobility-create-self-0001",
        trace=trace(),
    )
    assert replay.request_id == created.request_id
    assert created.state is MobilityRideRequestState.DRAFT
    validated = service.validate(
        actor_account_id=account_id,
        request_id=created.request_id,
        expected_version=1,
        idempotency_key="mobility-validate-self-0001",
        trace=trace(),
    )
    submitted = service.submit(
        actor_account_id=account_id,
        request_id=created.request_id,
        expected_version=2,
        idempotency_key="mobility-submit-self-0001",
        trace=trace(),
    )
    assert validated.state is MobilityRideRequestState.VALIDATED
    assert submitted.state is MobilityRideRequestState.SUBMITTED
    restarted = PassengerMobilityRideRequestService(postgres_engine).get_authorized(
        actor_account_id=account_id, request_id=created.request_id
    )
    assert restarted == submitted
    with postgres_engine.connect() as connection:
        event_types = tuple(
            connection.execute(
                select(persistence_domain_events.c.event_type)
                .where(
                    persistence_domain_events.c.aggregate_id == str(created.request_id)
                )
                .order_by(persistence_domain_events.c.occurred_at)
            ).scalars()
        )
        assert event_types == (
            "mobility.ride_request_created",
            "mobility.ride_request_validated",
            "mobility.ride_request_submitted",
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(persistence_outbox)
                .join(
                    persistence_domain_events,
                    persistence_domain_events.c.event_id
                    == persistence_outbox.c.event_id,
                )
                .where(
                    persistence_domain_events.c.aggregate_id == str(created.request_id)
                )
            ).scalar_one()
            == 3
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.resource_id == str(created.request_id))
            ).scalar_one()
            == 3
        )


def test_trusted_passenger_scheduled_stops_and_household_rejection(postgres_engine):
    service = PassengerMobilityRideRequestService(postgres_engine)
    requester_account, requester_subject = account(postgres_engine)
    passenger_account, passenger_subject = account(postgres_engine)
    scheduled_for = datetime.now(UTC) + timedelta(days=1)
    scheduled = command(
        passenger_subject,
        schedule_intent=ScheduleIntentType.SCHEDULED,
        scheduled_for=scheduled_for,
    )
    with pytest.raises(RideRequestAuthorizationError):
        service.create_draft(
            actor_account_id=requester_account,
            command=scheduled,
            idempotency_key="mobility-create-trusted-0001",
            trace=trace(),
        )
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(customer_household_relationships).values(
                relationship_id=uuid4(),
                inviting_subject_id=requester_subject,
                invited_subject_id=passenger_subject,
                relationship_type=RelationshipType.FAMILY_MEMBER.value,
                state=RelationshipState.ACTIVE.value,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
    created = service.create_draft(
        actor_account_id=requester_account,
        command=scheduled,
        idempotency_key="mobility-create-trusted-0001",
        trace=trace(),
    )
    assert created.passenger_subject_id == passenger_subject
    assert created.scheduled_for == scheduled_for
    assert created.stop_references == ("place:addis-meskel",)
    passenger_view = service.get_authorized(
        actor_account_id=passenger_account, request_id=created.request_id
    )
    assert passenger_view.request_id == created.request_id


@pytest.mark.parametrize(
    "relationship_state",
    [
        RelationshipState.PENDING,
        RelationshipState.SUSPENDED,
        RelationshipState.REMOVED,
    ],
)
def test_non_active_household_relationship_cannot_authorize_passenger(
    postgres_engine, relationship_state
):
    service = PassengerMobilityRideRequestService(postgres_engine)
    requester_account, requester_subject = account(postgres_engine)
    _, passenger_subject = account(postgres_engine)
    now = datetime.now(UTC)
    with postgres_engine.begin() as connection:
        connection.execute(
            insert(customer_household_relationships).values(
                relationship_id=uuid4(),
                inviting_subject_id=requester_subject,
                invited_subject_id=passenger_subject,
                relationship_type=RelationshipType.FAMILY_MEMBER.value,
                state=relationship_state.value,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )
    with pytest.raises(RideRequestAuthorizationError):
        service.create_draft(
            actor_account_id=requester_account,
            command=command(passenger_subject),
            idempotency_key=f"mobility-reject-{relationship_state.value}-0001",
            trace=trace(),
        )


def test_request_expires_only_after_recorded_expiry(postgres_engine):
    service = PassengerMobilityRideRequestService(postgres_engine)
    account_id, subject_id = account(postgres_engine)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    created = service.create_draft(
        actor_account_id=account_id,
        command=command(subject_id, expires_at=expires_at),
        idempotency_key="mobility-create-expiry-0001",
        trace=trace(),
    )
    with pytest.raises(ValueError, match="has not reached expiry"):
        service.expire(
            actor_account_id=account_id,
            request_id=created.request_id,
            expected_version=1,
            idempotency_key="mobility-expire-early-0001",
            trace=trace(),
            at=expires_at - timedelta(seconds=1),
        )
    expired = service.expire(
        actor_account_id=account_id,
        request_id=created.request_id,
        expected_version=1,
        idempotency_key="mobility-expire-0001",
        trace=trace(),
        at=expires_at,
    )
    assert expired.state is MobilityRideRequestState.EXPIRED


def test_conflicting_idempotency_stale_version_rollback_and_withdraw(postgres_engine):
    service = PassengerMobilityRideRequestService(postgres_engine)
    account_id, subject_id = account(postgres_engine)
    first = command(subject_id)
    created = service.create_draft(
        actor_account_id=account_id,
        command=first,
        idempotency_key="mobility-create-conflict-0001",
        trace=trace(),
    )
    with pytest.raises(IdempotencyConflictError):
        service.create_draft(
            actor_account_id=account_id,
            command=first.model_copy(update={"passenger_count": 3}),
            idempotency_key="mobility-create-conflict-0001",
            trace=trace(),
        )
    with pytest.raises(ValueError, match="Stale"):
        service.validate(
            actor_account_id=account_id,
            request_id=created.request_id,
            expected_version=9,
            idempotency_key="mobility-validate-stale-0001",
            trace=trace(),
        )
    current = service.get_authorized(
        actor_account_id=account_id, request_id=created.request_id
    )
    assert current.version == 1 and current.state is MobilityRideRequestState.DRAFT
    withdrawn = service.withdraw(
        actor_account_id=account_id,
        request_id=created.request_id,
        expected_version=1,
        idempotency_key="mobility-withdraw-0001",
        trace=trace(),
    )
    assert withdrawn.state is MobilityRideRequestState.WITHDRAWN
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(persistence_idempotency_records)
                .where(
                    persistence_idempotency_records.c.idempotency_key
                    == "mobility-validate-stale-0001"
                )
            ).scalar_one()
            == 0
        )
        row = (
            connection.execute(
                select(canonical_ride_requests).where(
                    canonical_ride_requests.c.request_id == created.request_id
                )
            )
            .mappings()
            .one()
        )
        assert row["mobility_model_version"] == 2
        assert row["rider_identity_id"] is None
