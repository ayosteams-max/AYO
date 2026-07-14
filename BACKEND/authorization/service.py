from datetime import UTC, datetime
from uuid import UUID

from BACKEND.audit.models import AuditEvent, AuditOutcome
from BACKEND.authorization.contracts import (
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationSubject,
)
from BACKEND.authorization.models import Role, RoleAssignment
from BACKEND.persistence.composition import AyoPostgresUnitOfWork


class AuthorizationService:
    """Policy decision point for RBAC checks inside the modular monolith."""

    def authorize(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        allowed = unit_of_work.authorization.has_permission(
            request.subject.identity_id,
            request.permission,
            at=request.occurred_at,
        )
        decision = AuthorizationDecision(
            allowed=allowed,
            reason="permission_granted" if allowed else "permission_denied",
        )
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=request.subject.actor_type,
                actor_id=str(request.subject.identity_id),
                session_id=request.subject.session_id,
                action=("authorization.allowed" if allowed else "authorization.denied"),
                resource_type=request.resource_type,
                resource_id=request.resource_id,
                outcome=AuditOutcome.SUCCESS if allowed else AuditOutcome.DENIED,
                reason=decision.reason,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                source_module="authorization",
                safe_metadata={
                    "category": "authorization",
                    "operation": request.permission,
                },
            )
        )
        return decision

    def require(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        request: AuthorizationRequest,
    ) -> None:
        decision = self.authorize(unit_of_work, request)
        if not decision.allowed:
            raise PermissionError("Authorization denied")


class AuthorizationAdministrationService:
    """Audited RBAC administration inside one transaction boundary."""

    def create_role(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        role: Role,
        actor: AuthorizationSubject,
        correlation_id: UUID,
    ) -> Role:
        self._require_administration_permission(
            unit_of_work,
            actor=actor,
            permission="authorization.roles.manage",
            correlation_id=correlation_id,
        )
        created = unit_of_work.authorization.create_role(role)
        self._audit(
            unit_of_work,
            actor=actor,
            action="authorization.role.created",
            resource_type="role",
            resource_id=str(created.role_id),
            correlation_id=correlation_id,
            operation="role_create",
        )
        return created

    def grant_permission(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        role_id: UUID,
        permission_id: UUID,
        granted_at: datetime,
        actor: AuthorizationSubject,
        correlation_id: UUID,
    ) -> None:
        self._require_administration_permission(
            unit_of_work,
            actor=actor,
            permission="authorization.roles.manage",
            correlation_id=correlation_id,
        )
        unit_of_work.authorization.grant_permission(
            role_id, permission_id, granted_at=granted_at
        )
        self._audit(
            unit_of_work,
            actor=actor,
            action="authorization.permission.granted",
            resource_type="role",
            resource_id=str(role_id),
            correlation_id=correlation_id,
            operation="permission_grant",
        )

    def assign_role(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        assignment: RoleAssignment,
        actor: AuthorizationSubject,
        correlation_id: UUID,
    ) -> RoleAssignment:
        self._require_administration_permission(
            unit_of_work,
            actor=actor,
            permission="authorization.assignments.manage",
            correlation_id=correlation_id,
        )
        created = unit_of_work.authorization.assign_role(assignment)
        self._audit(
            unit_of_work,
            actor=actor,
            action="authorization.role.assigned",
            resource_type="identity",
            resource_id=str(created.identity_id),
            correlation_id=correlation_id,
            operation="role_assign",
        )
        return created

    def revoke_assignment(
        self,
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        assignment_id: UUID,
        revoked_at: datetime,
        reason: str,
        actor: AuthorizationSubject,
        correlation_id: UUID,
    ) -> RoleAssignment | None:
        self._require_administration_permission(
            unit_of_work,
            actor=actor,
            permission="authorization.assignments.manage",
            correlation_id=correlation_id,
        )
        revoked = unit_of_work.authorization.revoke_assignment(
            assignment_id,
            revoked_at=revoked_at,
            revoked_by_identity_id=actor.identity_id,
            reason=reason,
        )
        if revoked is not None:
            self._audit(
                unit_of_work,
                actor=actor,
                action="authorization.role.revoked",
                resource_type="identity",
                resource_id=str(revoked.identity_id),
                correlation_id=correlation_id,
                operation="role_revoke",
            )
        return revoked

    @staticmethod
    def _require_administration_permission(
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        actor: AuthorizationSubject,
        permission: str,
        correlation_id: UUID,
    ) -> None:
        AuthorizationService().require(
            unit_of_work,
            AuthorizationRequest(
                subject=actor,
                permission=permission,
                resource_type="authorization_control",
                occurred_at=datetime.now(UTC),
                correlation_id=correlation_id,
            ),
        )

    @staticmethod
    def _audit(
        unit_of_work: AyoPostgresUnitOfWork,
        *,
        actor: AuthorizationSubject,
        action: str,
        resource_type: str,
        resource_id: str,
        correlation_id: UUID,
        operation: str,
    ) -> None:
        unit_of_work.audit_events.append(
            AuditEvent(
                actor_type=actor.actor_type,
                actor_id=str(actor.identity_id),
                session_id=actor.session_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=correlation_id,
                source_module="authorization",
                safe_metadata={
                    "category": "authorization",
                    "operation": operation,
                },
            )
        )
