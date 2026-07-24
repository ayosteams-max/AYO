from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from BACKEND.customer_profile.models import (
    ProfileLifecycle,
    RelationshipState,
    RelationshipType,
)
from BACKEND.customer_profile.service import CustomerProfileService
from BACKEND.persistence.customer_profile_repository import CustomerProfileConflict
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.tables import (
    audit_events,
    canonical_subjects,
    customer_profiles,
    persistence_domain_events,
    persistence_outbox,
)
from BACKEND.persistence.trace import TraceContext

pytestmark = [pytest.mark.integration, pytest.mark.customer_profile]


def trace() -> TraceContext:
    return TraceContext.new().child(command_id=uuid4())


def subject(engine):
    subject_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(canonical_subjects).values(
                subject_id=subject_id,
                subject_kind="human",
                created_at=datetime.now(UTC),
                version=1,
            )
        )
    return subject_id


def create_profile(service, subject_id, *, key="profile-create-0001"):
    return service.create_profile(
        actor_subject_id=subject_id,
        display_name="Abebe Kebede",
        preferred_name="Abebe",
        language="am-ET",
        region="ET",
        timezone="Africa/Addis_Ababa",
        service_area_preference="addis-ababa",
        profile_image_reference="media/profile/opaque-1",
        idempotency_key=key,
        trace=trace(),
    )


def test_profile_create_retry_update_concurrency_and_atomic_evidence(postgres_engine):
    service, subject_id = (
        CustomerProfileService(postgres_engine),
        subject(postgres_engine),
    )
    created = create_profile(service, subject_id)
    replay = create_profile(service, subject_id)
    assert replay.profile_id == created.profile_id
    with pytest.raises(CustomerProfileConflict):
        create_profile(service, subject_id, key="profile-create-0002")
    updated = service.update_profile(
        actor_subject_id=subject_id,
        expected_version=1,
        preferred_name="Abi",
        idempotency_key="profile-update-0001",
        trace=trace(),
    )
    assert updated.preferred_name == "Abi" and updated.version == 2
    with pytest.raises(OptimisticConcurrencyError):
        service.update_profile(
            actor_subject_id=subject_id,
            expected_version=1,
            language="en-ET",
            idempotency_key="profile-update-0002",
            trace=trace(),
        )
    suspended = service.transition_profile(
        actor_subject_id=subject_id,
        target=ProfileLifecycle.SUSPENDED,
        expected_version=2,
        idempotency_key="profile-suspend-0001",
        trace=trace(),
    )
    closed = service.transition_profile(
        actor_subject_id=subject_id,
        target=ProfileLifecycle.CLOSED,
        expected_version=3,
        idempotency_key="profile-close-0001",
        trace=trace(),
    )
    assert suspended.state is ProfileLifecycle.SUSPENDED
    assert closed.state is ProfileLifecycle.CLOSED
    with pytest.raises(ValueError):
        service.transition_profile(
            actor_subject_id=subject_id,
            target=ProfileLifecycle.ACTIVE,
            expected_version=4,
            idempotency_key="profile-reopen-invalid",
            trace=trace(),
        )
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(customer_profiles)
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(audit_events)
                .where(audit_events.c.source_module == "customer_profile")
            ).scalar_one()
            == 4
        )
        assert (
            connection.execute(
                select(func.count())
                .select_from(persistence_domain_events)
                .where(persistence_domain_events.c.source_module == "customer_profile")
            ).scalar_one()
            == 4
        )
        assert (
            connection.execute(
                select(func.count()).select_from(persistence_outbox)
            ).scalar_one()
            == 4
        )


def test_household_consent_lifecycle_and_book_for_other_validation(postgres_engine):
    service = CustomerProfileService(postgres_engine)
    inviter, invited, stranger = (
        subject(postgres_engine),
        subject(postgres_engine),
        subject(postgres_engine),
    )
    relationship = service.invite_relationship(
        actor_subject_id=inviter,
        invited_subject_id=invited,
        relationship_type=RelationshipType.CAREGIVER,
        idempotency_key="household-invite-0001",
        trace=trace(),
    )
    assert not service.validate_intended_passenger(
        actor_subject_id=inviter, intended_subject_id=invited
    )
    with pytest.raises(PermissionError):
        service.transition_relationship(
            actor_subject_id=inviter,
            relationship_id=relationship.relationship_id,
            target=RelationshipState.ACTIVE,
            expected_version=1,
            idempotency_key="household-activate-bad",
            trace=trace(),
        )
    active = service.transition_relationship(
        actor_subject_id=invited,
        relationship_id=relationship.relationship_id,
        target=RelationshipState.ACTIVE,
        expected_version=1,
        idempotency_key="household-activate-0001",
        trace=trace(),
    )
    assert service.validate_intended_passenger(
        actor_subject_id=inviter, intended_subject_id=invited
    )
    assert service.validate_intended_passenger(
        actor_subject_id=invited, intended_subject_id=inviter
    )
    assert not service.validate_intended_passenger(
        actor_subject_id=stranger, intended_subject_id=invited
    )
    suspended = service.transition_relationship(
        actor_subject_id=inviter,
        relationship_id=active.relationship_id,
        target=RelationshipState.SUSPENDED,
        expected_version=2,
        idempotency_key="household-suspend-0001",
        trace=trace(),
    )
    assert not service.validate_intended_passenger(
        actor_subject_id=inviter, intended_subject_id=invited
    )
    removed = service.transition_relationship(
        actor_subject_id=invited,
        relationship_id=suspended.relationship_id,
        target=RelationshipState.REMOVED,
        expected_version=3,
        idempotency_key="household-remove-0001",
        trace=trace(),
    )
    with pytest.raises(ValueError):
        service.transition_relationship(
            actor_subject_id=invited,
            relationship_id=removed.relationship_id,
            target=RelationshipState.ACTIVE,
            expected_version=4,
            idempotency_key="household-reactivate-bad",
            trace=trace(),
        )


def test_emergency_contact_priority_ownership_and_activation(postgres_engine):
    service, owner, other = (
        CustomerProfileService(postgres_engine),
        subject(postgres_engine),
        subject(postgres_engine),
    )
    contact = service.add_emergency_contact(
        actor_subject_id=owner,
        display_name="Trusted Contact",
        channel_reference="contact-channel/opaque-1",
        priority=1,
        contact_subject_id=other,
        idempotency_key="emergency-create-0001",
        trace=trace(),
    )
    replay = service.add_emergency_contact(
        actor_subject_id=owner,
        display_name="Trusted Contact",
        channel_reference="contact-channel/opaque-1",
        priority=1,
        contact_subject_id=other,
        idempotency_key="emergency-create-0001",
        trace=trace(),
    )
    assert replay.contact_id == contact.contact_id
    with pytest.raises(PermissionError):
        service.set_emergency_contact_active(
            actor_subject_id=other,
            contact_id=contact.contact_id,
            active=False,
            expected_version=1,
            idempotency_key="emergency-disable-bad",
            trace=trace(),
        )
    disabled = service.set_emergency_contact_active(
        actor_subject_id=owner,
        contact_id=contact.contact_id,
        active=False,
        expected_version=1,
        idempotency_key="emergency-disable-0001",
        trace=trace(),
    )
    assert not disabled.active and disabled.version == 2


def test_concurrent_household_activation_has_one_winner(postgres_engine):
    service = CustomerProfileService(postgres_engine)
    inviter, invited = subject(postgres_engine), subject(postgres_engine)
    relationship = service.invite_relationship(
        actor_subject_id=inviter,
        invited_subject_id=invited,
        relationship_type=RelationshipType.FAMILY_MEMBER,
        idempotency_key="household-concurrent-invite",
        trace=trace(),
    )

    def activate(number):
        try:
            service.transition_relationship(
                actor_subject_id=invited,
                relationship_id=relationship.relationship_id,
                target=RelationshipState.ACTIVE,
                expected_version=1,
                idempotency_key=f"household-concurrent-{number}",
                trace=trace(),
            )
            return "ok"
        except (OptimisticConcurrencyError, ValueError):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, (1, 2)))
    assert results.count("ok") == 1


def test_rollback_and_restart_persistence(postgres_engine, monkeypatch):
    service, subject_id = (
        CustomerProfileService(postgres_engine),
        subject(postgres_engine),
    )
    original = service._record

    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(service, "_record", fail)
    with pytest.raises(RuntimeError, match="injected"):
        create_profile(service, subject_id, key="profile-rollback-0001")
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(customer_profiles)
            ).scalar_one()
            == 0
        )
    monkeypatch.setattr(service, "_record", original)
    created = create_profile(service, subject_id, key="profile-restart-0001")
    postgres_engine.dispose()
    loaded = CustomerProfileService(postgres_engine)
    with loaded._uow() as unit:
        persisted = unit.profiles.profile_for_subject(subject_id)
    assert persisted is not None and persisted.profile_id == created.profile_id
