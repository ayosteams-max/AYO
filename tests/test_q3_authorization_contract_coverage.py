from contextlib import AbstractContextManager
from datetime import UTC, datetime
from types import SimpleNamespace, TracebackType
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from BACKEND.audit.models import ActorType, AuditOutcome
from BACKEND.authorization.contracts import (
    AuthorizationRequest,
    AuthorizationSubject,
)
from BACKEND.authorization.enforcement import (
    AuthorizationEnforcer,
    DenyAllOwnershipResolver,
    PermissionRequirement,
    ResourceOwnershipResolver,
)
from BACKEND.authorization.models import Role, RoleAssignment
from BACKEND.authorization.service import (
    AuthorizationAdministrationService,
    AuthorizationService,
)
from BACKEND.identity.models import IdentityType
from BACKEND.observability import InMemoryMetricsSink

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


class _Context(AbstractContextManager[Any]):
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def __enter__(self) -> Any:
        return self.unit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class _Composition:
    def __init__(self, unit: Any) -> None:
        self.unit = unit

    def unit_of_work(self) -> _Context:
        return _Context(self.unit)


def _subject() -> AuthorizationSubject:
    return AuthorizationSubject(
        identity_id=uuid4(),
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )


def _request(subject: AuthorizationSubject) -> AuthorizationRequest:
    return AuthorizationRequest(
        subject=subject,
        permission="merchant.dashboard.read_own",
        resource_type="merchant",
        resource_id=str(uuid4()),
        occurred_at=NOW,
        correlation_id=uuid4(),
    )


def _unit(allowed: bool = True) -> Any:
    unit = MagicMock()
    unit.audit_events = []
    unit.authorization.has_permission.return_value = allowed
    return unit


@pytest.mark.parametrize("allowed", [True, False])
def test_authorization_decision_and_audit_are_atomic_and_fail_closed(
    allowed: bool,
) -> None:
    unit = _unit(allowed)
    request = _request(_subject())
    service = AuthorizationService()
    decision = service.authorize(unit, request)
    assert decision.allowed is allowed
    assert decision.reason == ("permission_granted" if allowed else "permission_denied")
    assert unit.audit_events[0].outcome is (
        AuditOutcome.SUCCESS if allowed else AuditOutcome.DENIED
    )
    assert unit.audit_events[0].safe_metadata == {
        "category": "authorization",
        "operation": request.permission,
    }
    if allowed:
        service.require(unit, request)
    else:
        with pytest.raises(PermissionError, match="Authorization denied"):
            service.require(unit, request)


def test_authorization_administration_requires_permission_and_preserves_evidence() -> (
    None
):
    actor = _subject()
    role = Role(
        code="merchant_manager",
        description="Merchant manager",
        created_at=NOW,
    )
    assignment = RoleAssignment(
        identity_id=uuid4(),
        role_id=role.role_id,
        assigned_by_identity_id=actor.identity_id,
        assigned_at=NOW,
    )
    unit = _unit(False)
    service = AuthorizationAdministrationService()
    with pytest.raises(PermissionError):
        service.create_role(unit, role=role, actor=actor, correlation_id=uuid4())

    unit.authorization.has_permission.return_value = True
    unit.authorization.create_role.return_value = role
    assert (
        service.create_role(unit, role=role, actor=actor, correlation_id=uuid4())
        == role
    )
    service.grant_permission(
        unit,
        role_id=role.role_id,
        permission_id=uuid4(),
        granted_at=NOW,
        actor=actor,
        correlation_id=uuid4(),
    )
    unit.authorization.assign_role.return_value = assignment
    assert (
        service.assign_role(
            unit, assignment=assignment, actor=actor, correlation_id=uuid4()
        )
        == assignment
    )
    unit.authorization.revoke_assignment.return_value = assignment.model_copy(
        update={
            "revoked_at": NOW,
            "revoked_by_identity_id": actor.identity_id,
            "revocation_reason": "governed_revoke",
        }
    )
    assert (
        service.revoke_assignment(
            unit,
            assignment_id=assignment.assignment_id,
            revoked_at=NOW,
            reason="governed_revoke",
            actor=actor,
            correlation_id=uuid4(),
        )
        is not None
    )
    unit.authorization.revoke_assignment.return_value = None
    assert (
        service.revoke_assignment(
            unit,
            assignment_id=uuid4(),
            revoked_at=NOW,
            reason="already_revoked",
            actor=actor,
            correlation_id=uuid4(),
        )
        is None
    )
    assert {event.safe_metadata["operation"] for event in unit.audit_events} >= {
        "role_create",
        "permission_grant",
        "role_assign",
        "role_revoke",
    }


def _starlette_request(
    *,
    subject: AuthorizationSubject | None,
    resource_id: str | None = None,
) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/resource",
            "headers": [],
            "query_string": b"",
            "path_params": {} if resource_id is None else {"resource_id": resource_id},
            "server": ("test", 80),
            "client": ("test", 1),
            "scheme": "http",
        }
    )
    request.state.authorization_subject = subject
    request.state.authorization_correlation_id = uuid4()
    return request


def test_enforcer_distinguishes_authentication_permission_and_ownership() -> None:
    unit = _unit(True)
    metrics = InMemoryMetricsSink()
    enforcer = AuthorizationEnforcer(_Composition(unit), metrics=metrics)  # type: ignore[arg-type]
    basic = PermissionRequirement(
        permission="merchant.dashboard.read_own", resource_type="merchant"
    )
    with pytest.raises(HTTPException) as unauthenticated:
        enforcer.enforce(_starlette_request(subject=None), basic)
    assert unauthenticated.value.status_code == 401

    subject = _subject()
    unit.authorization.has_permission.return_value = False
    with pytest.raises(HTTPException) as denied:
        enforcer.enforce(_starlette_request(subject=subject), basic)
    assert denied.value.status_code == 403

    ownership = PermissionRequirement(
        permission="merchant.dashboard.read_own",
        resource_type="merchant",
        resource_id_parameter="resource_id",
        ownership_required=True,
    )
    with pytest.raises(RuntimeError, match="requires a resource ID"):
        enforcer.enforce(_starlette_request(subject=subject), ownership)
    with pytest.raises(HTTPException) as mismatch:
        enforcer.enforce(
            _starlette_request(subject=subject, resource_id=str(uuid4())), ownership
        )
    assert mismatch.value.status_code == 403
    assert unit.audit_events[-1].reason == "ownership_mismatch"


def test_enforcer_allows_source_owned_resource_and_default_resolver_denies() -> None:
    subject = _subject()
    unit = _unit(True)
    owner = SimpleNamespace(owner_identity_id=lambda **_: subject.identity_id)
    enforcer = AuthorizationEnforcer(
        _Composition(unit),  # type: ignore[arg-type]
        ownership_resolver=owner,
    )
    requirement = PermissionRequirement(
        permission="merchant.dashboard.read_own",
        resource_type="merchant",
        resource_id_parameter="resource_id",
        ownership_required=True,
    )
    enforcer.enforce(
        _starlette_request(subject=subject, resource_id=str(uuid4())), requirement
    )
    assert unit.audit_events[-1].action == "authorization.allowed"
    deny_all: ResourceOwnershipResolver = DenyAllOwnershipResolver()
    assert (
        deny_all.owner_identity_id(resource_type="merchant", resource_id=str(uuid4()))
        is None
    )
