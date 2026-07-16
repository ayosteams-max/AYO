import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationSubject,
)
from BACKEND.authorization.enforcement import (
    AnonymousSubjectResolver,
    permission_required,
)
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.authorization.registry import (
    AI_SUPPORT_PERMISSION_SET,
    PERMISSION_REGISTRY,
)
from BACKEND.identity.models import IdentityType


def test_permission_and_role_codes_are_bounded_and_registry_is_immutable() -> None:
    now = datetime.now(UTC)
    permission = Permission(
        code="rides.read",
        description="Read a ride.",
        created_at=now,
    )
    role = Role(code="rider", description="Rider role.", created_at=now)
    assert permission.code == "rides.read"
    assert role.version == 1
    assert "authorization.roles.manage" in PERMISSION_REGISTRY
    with pytest.raises(TypeError):
        PERMISSION_REGISTRY["unsafe.new"] = "Not permitted"  # type: ignore[index]
    with pytest.raises(ValidationError):
        Permission(code="INVALID ROLE", description="Invalid.", created_at=now)
    with pytest.raises(ValidationError, match="timezone-aware"):
        Permission(
            code="rides.read", description="Invalid time.", created_at=datetime.now()
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        Role(code="rider", description="Invalid time.", created_at=datetime.now())


def test_role_assignment_lifecycle_is_explicit_and_timezone_safe() -> None:
    now = datetime.now(UTC)
    assignment = RoleAssignment(
        identity_id=uuid4(),
        role_id=uuid4(),
        assigned_by_identity_id=uuid4(),
        assigned_at=now,
        expires_at=now + timedelta(hours=1),
    )
    assert assignment.active_at(now)
    assert not assignment.active_at(now + timedelta(hours=2))
    with pytest.raises(ValueError, match="timezone-aware"):
        assignment.active_at(datetime.now())
    with pytest.raises(ValidationError, match="expiry"):
        RoleAssignment(
            identity_id=uuid4(),
            role_id=uuid4(),
            assigned_by_identity_id=uuid4(),
            assigned_at=now,
            expires_at=now,
        )
    with pytest.raises(ValidationError, match="revocation fields"):
        RoleAssignment.model_validate({**assignment.model_dump(), "revoked_at": now})


def test_policy_shaped_request_separates_identity_and_permission() -> None:
    subject = AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.STAFF,
        actor_type=ActorType.STAFF,
    )
    request = AuthorizationRequest(
        subject=subject,
        permission="authorization.roles.read",
        resource_type="role",
        resource_id=str(uuid4()),
        occurred_at=datetime.now(UTC),
        correlation_id=uuid4(),
    )
    assert request.subject.identity_id == subject.identity_id
    assert not AuthorizationDecision(allowed=False, reason="permission_denied").allowed
    with pytest.raises(ValidationError, match="actor type"):
        AuthorizationSubject(
            identity_id=uuid4(),
            identity_type=IdentityType.ADMINISTRATOR,
            actor_type=ActorType.RIDER,
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        AuthorizationRequest.model_validate(
            {**request.model_dump(), "occurred_at": datetime.now()}
        )


def test_permission_decorator_records_policy_without_enforcing_it_early() -> None:
    @permission_required("rides.read", resource_type="ride")
    def endpoint() -> None:
        return None

    requirement = endpoint.__ayo_permission_requirement__  # type: ignore[attr-defined]
    assert requirement.permission == "rides.read"
    assert requirement.resource_type == "ride"
    assert not requirement.ownership_required
    assert asyncio.run(AnonymousSubjectResolver().resolve(object())) is None  # type: ignore[arg-type]


def test_ai_support_permission_set_is_explicit_and_non_privileged() -> None:
    assert set(PERMISSION_REGISTRY) >= AI_SUPPORT_PERMISSION_SET
    assert {
        "support.case.create",
        "support.case.read_assigned",
        "support.case.update",
        "support.case.escalate",
        "support.trip.read_limited",
        "support.payment.read_status",
        "support.account.read_limited",
        "support.guidance.provide",
    } == AI_SUPPORT_PERMISSION_SET
    prohibited_fragments = {
        "admin",
        "audit",
        "payment.release",
        "payment.reverse",
        "payout",
        "identity.update",
        "account.delete",
        "account.suspend",
        "safety.override",
        "fraud.override",
    }
    assert not any(
        fragment in permission
        for permission in AI_SUPPORT_PERMISSION_SET
        for fragment in prohibited_fragments
    )
