from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from BACKEND.audit.models import ActorType
from BACKEND.authorization.models import Permission, Role, RoleAssignment
from BACKEND.identity.models import AssuranceLevel, IdentityType


class AuthorizationSubject(BaseModel):
    """Trusted server context; never construct this from caller role claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity_id: UUID
    identity_type: IdentityType
    actor_type: ActorType
    session_id: UUID | None = None
    assurance_level: AssuranceLevel = AssuranceLevel.BASIC

    @model_validator(mode="after")
    def actor_matches_identity_type(self) -> "AuthorizationSubject":
        expected = {
            IdentityType.ANONYMOUS: ActorType.ANONYMOUS,
            IdentityType.RIDER: ActorType.RIDER,
            IdentityType.DRIVER: ActorType.DRIVER,
            IdentityType.STAFF: ActorType.STAFF,
            IdentityType.ADMINISTRATOR: ActorType.ADMINISTRATOR,
            IdentityType.SERVICE: ActorType.SERVICE,
            IdentityType.MERCHANT: ActorType.SERVICE,
            IdentityType.SERVICE_PROVIDER: ActorType.SERVICE,
        }[self.identity_type]
        if self.actor_type is not expected:
            raise ValueError("Authorization actor type does not match identity type")
        return self


class AuthorizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: AuthorizationSubject
    permission: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)
    resource_id: str | None = Field(default=None, min_length=1, max_length=128)
    occurred_at: datetime
    correlation_id: UUID
    request_id: UUID | None = None

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Authorization decision time must be timezone-aware")
        return value.astimezone(UTC)


class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$", max_length=128)


class AuthorizationRepository(Protocol):
    def create_permission(self, permission: Permission) -> Permission: ...

    def create_role(self, role: Role) -> Role: ...

    def grant_permission(self, role_id: UUID, permission_id: UUID) -> None: ...

    def assign_role(self, assignment: RoleAssignment) -> RoleAssignment: ...

    def revoke_assignment(
        self,
        assignment_id: UUID,
        *,
        revoked_at: datetime,
        revoked_by_identity_id: UUID,
        reason: str,
    ) -> RoleAssignment | None: ...

    def has_permission(
        self, identity_id: UUID, permission: str, *, at: datetime
    ) -> bool: ...
