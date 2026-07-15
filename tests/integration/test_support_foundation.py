from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import AuthorizationSubject
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.tables import audit_events, permissions, support_case_events
from BACKEND.support.models import (
    MessageVisibility,
    RequesterType,
    RetentionClassification,
    SupportCase,
    SupportCategory,
    SupportChannel,
    SupportMessage,
    SupportQueue,
    SupportStatus,
)
from BACKEND.support.service import SupportAccessDenied, SupportService

pytestmark = [pytest.mark.integration, pytest.mark.support]


def identity(composition, identity_type: IdentityType) -> Identity:
    now = datetime.now(UTC)
    value = Identity(
        identity_type=identity_type,
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    with composition.unit_of_work() as unit_of_work:
        unit_of_work.identities.create(value)
    return value


def subject(value: Identity) -> AuthorizationSubject:
    actor = {
        IdentityType.RIDER: ActorType.RIDER,
        IdentityType.DRIVER: ActorType.DRIVER,
        IdentityType.STAFF: ActorType.STAFF,
        IdentityType.SERVICE: ActorType.SERVICE,
    }[value.identity_type]
    return AuthorizationSubject(
        identity_id=value.identity_id,
        identity_type=value.identity_type,
        actor_type=actor,
    )


def support_case(requester: Identity, **changes) -> SupportCase:
    now = datetime.now(UTC)
    values = {
        "requester_identity_id": requester.identity_id,
        "requester_type": RequesterType(requester.identity_type.value),
        "source_channel": SupportChannel.IN_APP_CHAT,
        "category": SupportCategory.GENERAL_INFORMATION,
        "correlation_id": uuid4(),
        "idempotency_key": f"case-{uuid4()}",
        "created_at": now,
        "updated_at": now,
        "retention_classification": RetentionClassification.ROUTINE_SUPPORT,
    }
    return SupportCase(**(values | changes))


def grant(composition, person: Identity, code: str) -> None:
    now = datetime.now(UTC)
    permission = Permission(code=code, description="Test permission.", created_at=now)
    role = Role(code=f"test.{uuid4().hex}", description="Test role.", created_at=now)
    with composition.unit_of_work() as unit_of_work:
        permission_id = unit_of_work.connection.execute(
            select(permissions.c.permission_id).where(permissions.c.code == code)
        ).scalar_one_or_none()
        if permission_id is None:
            unit_of_work.authorization.create_permission(permission)
            permission_id = permission.permission_id
        unit_of_work.authorization.create_role(role)
        unit_of_work.authorization.grant_permission(
            role.role_id, permission_id, granted_at=now
        )
        unit_of_work.authorization.assign_role(
            RoleAssignment(
                identity_id=person.identity_id,
                role_id=role.role_id,
                assigned_by_identity_id=person.identity_id,
                assigned_at=now,
            )
        )


def test_case_creation_is_idempotent_atomic_and_audited(
    postgres_composition, postgres_engine
) -> None:
    rider = identity(postgres_composition, IdentityType.RIDER)
    value = support_case(rider)
    service = SupportService()
    with postgres_composition.unit_of_work() as unit_of_work:
        first = service.create_case(unit_of_work, value, actor=subject(rider))
        second = service.create_case(unit_of_work, value, actor=subject(rider))
    assert first.case_id == second.case_id
    with postgres_engine.connect() as connection:
        assert len(connection.execute(select(support_case_events)).all()) == 1
        assert len(connection.execute(select(audit_events)).all()) == 1

    rolled_back = support_case(rider)
    with (
        pytest.raises(RuntimeError),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        service.create_case(unit_of_work, rolled_back, actor=subject(rider))
        raise RuntimeError("rollback")
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.support.get_case(rolled_back.case_id) is None


def test_customer_ai_and_queue_resource_boundaries(postgres_composition) -> None:
    rider = identity(postgres_composition, IdentityType.RIDER)
    other = identity(postgres_composition, IdentityType.RIDER)
    ai = identity(postgres_composition, IdentityType.SERVICE)
    staff = identity(postgres_composition, IdentityType.STAFF)
    grant(postgres_composition, ai, "support.case.read_assigned")
    grant(postgres_composition, staff, "support.queue.safety.access")
    value = support_case(
        rider,
        ai_service_identity_id=ai.identity_id,
        assigned_queue=SupportQueue.GENERAL,
    )
    service = SupportService()
    with postgres_composition.unit_of_work() as unit_of_work:
        value = service.create_case(unit_of_work, value, actor=subject(rider))
    with postgres_composition.unit_of_work() as unit_of_work:
        service.require_read(unit_of_work, value, subject(rider))
        service.require_read(unit_of_work, value, subject(ai))
        with pytest.raises(SupportAccessDenied):
            service.require_read(unit_of_work, value, subject(other))
        with pytest.raises(SupportAccessDenied):
            service.require_read(unit_of_work, value, subject(staff))


def test_messages_separate_internal_notes_and_case_updates_are_optimistic(
    postgres_composition,
) -> None:
    rider = identity(postgres_composition, IdentityType.RIDER)
    value = support_case(rider)
    with postgres_composition.unit_of_work() as unit_of_work:
        value, _ = unit_of_work.support.create_case(value)
        for visibility in (
            MessageVisibility.CUSTOMER_VISIBLE,
            MessageVisibility.INTERNAL_NOTE,
        ):
            unit_of_work.support.append_message(
                SupportMessage(
                    case_id=value.case_id,
                    author_identity_id=rider.identity_id,
                    visibility=visibility,
                    language_tag="am-ET",
                    content=f"Safe {visibility.value}",
                    created_at=datetime.now(UTC),
                )
            )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert (
            len(
                unit_of_work.support.list_messages(
                    value.case_id, include_internal=False
                )
            )
            == 1
        )
        assert (
            len(
                unit_of_work.support.list_messages(value.case_id, include_internal=True)
            )
            == 2
        )
        changed = value.model_copy(update={"updated_at": datetime.now(UTC)})
        unit_of_work.support.save_case(changed, expected_version=1)
        with pytest.raises(OptimisticConcurrencyError):
            unit_of_work.support.save_case(changed, expected_version=1)


def test_assignment_reassignment_escalation_resolution_and_closure(
    postgres_composition,
) -> None:
    rider = identity(postgres_composition, IdentityType.RIDER)
    first_staff = identity(postgres_composition, IdentityType.STAFF)
    second_staff = identity(postgres_composition, IdentityType.STAFF)
    grant(postgres_composition, first_staff, "support.queue.general.access")
    grant(postgres_composition, second_staff, "support.queue.general.access")
    grant(postgres_composition, second_staff, "support.queue.finance.access")
    value = support_case(rider)
    service = SupportService()
    with postgres_composition.unit_of_work() as unit_of_work:
        value = service.create_case(unit_of_work, value, actor=subject(rider))
    with postgres_composition.unit_of_work() as unit_of_work:
        value = service.assign(
            unit_of_work,
            value,
            actor=subject(first_staff),
            human_identity_id=first_staff.identity_id,
        )
        value = service.assign(
            unit_of_work,
            value,
            actor=subject(second_staff),
            human_identity_id=second_staff.identity_id,
        )
        value = service.escalate(
            unit_of_work,
            value,
            actor=subject(second_staff),
            queue=SupportQueue.FINANCE,
            reason="financial_review",
        )
        value = service.transition_case(
            unit_of_work,
            value,
            actor=subject(second_staff),
            target=SupportStatus.IN_PROGRESS,
        )
        value = service.transition_case(
            unit_of_work,
            value,
            actor=subject(second_staff),
            target=SupportStatus.RESOLVED,
            resolution_category="guidance_provided",
        )
        value = service.transition_case(
            unit_of_work,
            value,
            actor=subject(second_staff),
            target=SupportStatus.CLOSED,
        )
    assert value.assigned_human_identity_id == second_staff.identity_id
    assert value.status is SupportStatus.CLOSED
