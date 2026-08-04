from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.persistence.tables import (
    identities,
    identity_role_assignments,
    permissions,
    role_permissions,
    roles,
)


def _permission(row: Mapping[Any, Any]) -> Permission:
    return Permission.model_validate(dict(row))


def _role(row: Mapping[Any, Any]) -> Role:
    return Role.model_validate(dict(row))


def _assignment(row: Mapping[Any, Any]) -> RoleAssignment:
    return RoleAssignment.model_validate(dict(row))


class PostgresAuthorizationRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_permission(self, permission: Permission) -> Permission:
        row = (
            self._connection.execute(
                insert(permissions)
                .values(**permission.model_dump())
                .returning(permissions)
            )
            .mappings()
            .one()
        )
        return _permission(row)

    def create_role(self, role: Role) -> Role:
        row = (
            self._connection.execute(
                insert(roles).values(**role.model_dump()).returning(roles)
            )
            .mappings()
            .one()
        )
        return _role(row)

    def grant_permission(
        self,
        role_id: UUID,
        permission_id: UUID,
        *,
        granted_at: datetime | None = None,
    ) -> None:
        granted_at = granted_at or datetime.now(UTC)
        self._connection.execute(
            postgres_insert(role_permissions)
            .values(
                role_id=role_id,
                permission_id=permission_id,
                granted_at=granted_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    role_permissions.c.role_id,
                    role_permissions.c.permission_id,
                ]
            )
        )

    def assign_role(self, assignment: RoleAssignment) -> RoleAssignment:
        row = (
            self._connection.execute(
                insert(identity_role_assignments)
                .values(**assignment.model_dump())
                .returning(identity_role_assignments)
            )
            .mappings()
            .one()
        )
        return _assignment(row)

    def revoke_assignment(
        self,
        assignment_id: UUID,
        *,
        revoked_at: datetime,
        revoked_by_identity_id: UUID,
        reason: str,
    ) -> RoleAssignment | None:
        row = (
            self._connection.execute(
                update(identity_role_assignments)
                .where(
                    identity_role_assignments.c.assignment_id == assignment_id,
                    identity_role_assignments.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=revoked_at,
                    revoked_by_identity_id=revoked_by_identity_id,
                    revocation_reason=reason,
                )
                .returning(identity_role_assignments)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _assignment(row)

    def has_permission(
        self, identity_id: UUID, permission: str, *, at: datetime
    ) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Authorization decision time must be timezone-aware")
        statement = (
            select(role_permissions.c.role_id)
            .select_from(
                identities.join(
                    identity_role_assignments,
                    identities.c.identity_id == identity_role_assignments.c.identity_id,
                )
                .join(
                    role_permissions,
                    identity_role_assignments.c.role_id == role_permissions.c.role_id,
                )
                .join(
                    permissions,
                    role_permissions.c.permission_id == permissions.c.permission_id,
                )
            )
            .where(
                identities.c.identity_id == identity_id,
                identities.c.status == "active",
                permissions.c.code == permission,
                identity_role_assignments.c.revoked_at.is_(None),
                or_(
                    identity_role_assignments.c.expires_at.is_(None),
                    identity_role_assignments.c.expires_at > at,
                ),
            )
            .limit(1)
        )
        return self._connection.execute(statement).scalar_one_or_none() is not None
