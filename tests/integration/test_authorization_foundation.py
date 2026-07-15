from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from BACKEND.audit.models import ActorType
from BACKEND.authorization.contracts import (
    AuthorizationRequest,
    AuthorizationSubject,
)
from BACKEND.authorization.enforcement import (
    AnonymousSubjectResolver,
    AuthorizationContextMiddleware,
    AuthorizationEnforcer,
    AuthorizationRoute,
    permission_required,
    require_permission,
)
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.authorization.service import (
    AuthorizationAdministrationService,
    AuthorizationService,
)
from BACKEND.identity.models import AccountStatus, Identity, IdentityType
from BACKEND.persistence.tables import audit_events

pytestmark = [pytest.mark.integration, pytest.mark.authorization]


class TrustedTestSubjectResolver:
    def __init__(self, subject: AuthorizationSubject) -> None:
        self._subject = subject

    async def resolve(self, request: Request) -> AuthorizationSubject:
        del request
        return self._subject


def create_identity(postgres_composition, identity_type=IdentityType.RIDER) -> Identity:
    now = datetime.now(UTC)
    identity = Identity(
        identity_type=identity_type,
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.identities.create(identity)
    return identity


def provision_permission(
    postgres_composition,
    *,
    identity: Identity,
    permission_code: str = "test.resource.read",
) -> tuple[Permission, Role, RoleAssignment, AuthorizationSubject]:
    now = datetime.now(UTC)
    actor = AuthorizationSubject(
        identity_id=identity.identity_id,
        identity_type=identity.identity_type,
        actor_type=ActorType.RIDER,
    )
    permission = Permission(
        code=permission_code,
        description="Integration-test protected resource.",
        created_at=now,
    )
    role = Role(
        code=f"test.role.{uuid4().hex[:8]}", description="Test role.", created_at=now
    )
    assignment = RoleAssignment(
        identity_id=identity.identity_id,
        role_id=role.role_id,
        assigned_by_identity_id=identity.identity_id,
        assigned_at=now,
    )
    administration = AuthorizationAdministrationService()
    with postgres_composition.unit_of_work() as unit_of_work:
        unit_of_work.authorization.create_permission(permission)
        role_manage = unit_of_work.authorization.create_permission(
            Permission(
                code="authorization.roles.manage",
                description="Manage test roles.",
                created_at=now,
            )
        )
        assignment_manage = unit_of_work.authorization.create_permission(
            Permission(
                code="authorization.assignments.manage",
                description="Manage test assignments.",
                created_at=now,
            )
        )
        bootstrap_role = unit_of_work.authorization.create_role(
            Role(
                code=f"test.bootstrap.{uuid4().hex[:8]}",
                description="Test-only administration bootstrap.",
                created_at=now,
            )
        )
        unit_of_work.authorization.grant_permission(
            bootstrap_role.role_id, role_manage.permission_id, granted_at=now
        )
        unit_of_work.authorization.grant_permission(
            bootstrap_role.role_id, assignment_manage.permission_id, granted_at=now
        )
        unit_of_work.authorization.assign_role(
            RoleAssignment(
                identity_id=identity.identity_id,
                role_id=bootstrap_role.role_id,
                assigned_by_identity_id=identity.identity_id,
                assigned_at=now,
            )
        )
        administration.create_role(
            unit_of_work,
            role=role,
            actor=actor,
            correlation_id=uuid4(),
        )
        administration.grant_permission(
            unit_of_work,
            role_id=role.role_id,
            permission_id=permission.permission_id,
            granted_at=now,
            actor=actor,
            correlation_id=uuid4(),
        )
        administration.assign_role(
            unit_of_work,
            assignment=assignment,
            actor=actor,
            correlation_id=uuid4(),
        )
    return permission, role, assignment, actor


def authorization_request(identity: Identity, permission: str) -> AuthorizationRequest:
    return AuthorizationRequest(
        subject=AuthorizationSubject(
            identity_id=identity.identity_id,
            identity_type=identity.identity_type,
            actor_type=ActorType.RIDER,
        ),
        permission=permission,
        resource_type="test_resource",
        resource_id="resource-1",
        occurred_at=datetime.now(UTC),
        correlation_id=uuid4(),
    )


def test_deny_by_default_then_grant_revoke_and_audit(
    postgres_composition, postgres_engine
) -> None:
    identity = create_identity(postgres_composition)
    request = authorization_request(identity, "test.resource.read")
    service = AuthorizationService()
    with postgres_composition.unit_of_work() as unit_of_work:
        assert not service.authorize(unit_of_work, request).allowed

    permission, _, assignment, actor = provision_permission(
        postgres_composition, identity=identity
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert service.authorize(
            unit_of_work, authorization_request(identity, permission.code)
        ).allowed

    with postgres_composition.unit_of_work() as unit_of_work:
        AuthorizationAdministrationService().revoke_assignment(
            unit_of_work,
            assignment_id=assignment.assignment_id,
            revoked_at=datetime.now(UTC),
            reason="security_review",
            actor=actor,
            correlation_id=uuid4(),
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert not service.authorize(
            unit_of_work, authorization_request(identity, permission.code)
        ).allowed
    with postgres_engine.connect() as connection:
        actions = set(connection.execute(select(audit_events.c.action)).scalars())
    assert {
        "authorization.allowed",
        "authorization.denied",
        "authorization.role.assigned",
        "authorization.role.revoked",
    } <= actions


def test_expired_assignment_and_suspended_identity_are_denied(
    postgres_composition,
) -> None:
    identity = create_identity(postgres_composition)
    permission, role, _, actor = provision_permission(
        postgres_composition,
        identity=identity,
        permission_code="test.expiry.read",
    )
    other = create_identity(postgres_composition)
    expired = RoleAssignment(
        identity_id=other.identity_id,
        role_id=role.role_id,
        assigned_by_identity_id=identity.identity_id,
        assigned_at=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    with postgres_composition.unit_of_work() as unit_of_work:
        AuthorizationAdministrationService().assign_role(
            unit_of_work,
            assignment=expired,
            actor=actor,
            correlation_id=uuid4(),
        )
    service = AuthorizationService()
    with postgres_composition.unit_of_work() as unit_of_work:
        assert not service.authorize(
            unit_of_work, authorization_request(other, permission.code)
        ).allowed
        stored = unit_of_work.identities.get(identity.identity_id)
        unit_of_work.identities.save(
            stored.transition(AccountStatus.SUSPENDED, at=datetime.now(UTC)),
            expected_version=stored.version,
        )
    with postgres_composition.unit_of_work() as unit_of_work:
        assert not service.authorize(
            unit_of_work, authorization_request(identity, permission.code)
        ).allowed


def build_protected_app(postgres_composition, resolver) -> FastAPI:
    app = FastAPI()
    app.state.authorization_enforcer = AuthorizationEnforcer(postgres_composition)
    app.add_middleware(AuthorizationContextMiddleware, resolver=resolver)
    router = APIRouter(route_class=AuthorizationRoute)

    @router.get("/decorated/{resource_id}")
    @permission_required(
        "test.route.read",
        resource_type="test_resource",
        resource_id_parameter="resource_id",
    )
    def decorated(resource_id: str) -> dict[str, str]:
        return {"resource_id": resource_id}

    @router.get(
        "/dependency/{resource_id}",
        dependencies=[
            Depends(
                require_permission(
                    "test.route.read",
                    resource_type="test_resource",
                    resource_id_parameter="resource_id",
                )
            )
        ],
    )
    def dependency(resource_id: str) -> dict[str, str]:
        return {"resource_id": resource_id}

    app.include_router(router)
    return app


def test_middleware_decorator_and_dependency_enforce_real_rbac(
    postgres_composition,
) -> None:
    identity = create_identity(postgres_composition)
    _, _, _, subject = provision_permission(
        postgres_composition,
        identity=identity,
        permission_code="test.route.read",
    )
    authorized = TestClient(
        build_protected_app(postgres_composition, TrustedTestSubjectResolver(subject))
    )
    assert authorized.get("/decorated/one").status_code == 200
    assert authorized.get("/dependency/two").status_code == 200

    anonymous = TestClient(
        build_protected_app(postgres_composition, AnonymousSubjectResolver())
    )
    response = anonymous.get("/decorated/one")
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "authentication_required"}}

    denied_identity = create_identity(postgres_composition)
    denied_subject = AuthorizationSubject(
        identity_id=denied_identity.identity_id,
        identity_type=IdentityType.RIDER,
        actor_type=ActorType.RIDER,
    )
    denied = TestClient(
        build_protected_app(
            postgres_composition, TrustedTestSubjectResolver(denied_subject)
        )
    )
    response = denied.get("/decorated/one")
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "access_denied"}}


def test_authorization_and_audit_roll_back_together(postgres_composition) -> None:
    identity = create_identity(postgres_composition)
    permission, _, _, _ = provision_permission(
        postgres_composition,
        identity=identity,
        permission_code="test.rollback.read",
    )
    correlation_id = uuid4()
    request = authorization_request(identity, permission.code).model_copy(
        update={"correlation_id": correlation_id}
    )
    with (
        pytest.raises(RuntimeError, match="forced rollback"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        assert AuthorizationService().authorize(unit_of_work, request).allowed
        raise RuntimeError("forced rollback")
    with postgres_composition.unit_of_work() as unit_of_work:
        assert unit_of_work.audit_events.find_by_correlation(correlation_id) == []


def test_administration_service_cannot_bypass_rbac(postgres_composition) -> None:
    identity = create_identity(postgres_composition, IdentityType.STAFF)
    actor = AuthorizationSubject(
        identity_id=identity.identity_id,
        identity_type=IdentityType.STAFF,
        actor_type=ActorType.STAFF,
    )
    with (
        pytest.raises(PermissionError, match="Authorization denied"),
        postgres_composition.unit_of_work() as unit_of_work,
    ):
        AuthorizationAdministrationService().create_role(
            unit_of_work,
            role=Role(
                code="unauthorized.role",
                description="Must not be created.",
                created_at=datetime.now(UTC),
            ),
            actor=actor,
            correlation_id=uuid4(),
        )
