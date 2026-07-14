from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AuthorizationName = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)
]


class Permission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    permission_id: UUID = Field(default_factory=uuid4)
    code: AuthorizationName
    description: Annotated[str, Field(min_length=1, max_length=256)]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Permission creation time must be timezone-aware")
        return value.astimezone(UTC)


class Role(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role_id: UUID = Field(default_factory=uuid4)
    code: AuthorizationName
    description: Annotated[str, Field(min_length=1, max_length=256)]
    system_managed: bool = False
    created_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at")
    @classmethod
    def created_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Role creation time must be timezone-aware")
        return value.astimezone(UTC)


class RoleAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assignment_id: UUID = Field(default_factory=uuid4)
    identity_id: UUID
    role_id: UUID
    assigned_by_identity_id: UUID
    assigned_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_identity_id: UUID | None = None
    revocation_reason: AuthorizationName | None = None

    @field_validator("assigned_at", "expires_at", "revoked_at")
    @classmethod
    def timestamps_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Role-assignment timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> "RoleAssignment":
        if self.expires_at is not None and self.expires_at <= self.assigned_at:
            raise ValueError("Role-assignment expiry must follow assignment")
        revoked_fields = (
            self.revoked_at,
            self.revoked_by_identity_id,
            self.revocation_reason,
        )
        if any(value is not None for value in revoked_fields) and not all(
            value is not None for value in revoked_fields
        ):
            raise ValueError("Role-assignment revocation fields must be set together")
        return self

    def active_at(self, instant: datetime) -> bool:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Authorization decision time must be timezone-aware")
        instant = instant.astimezone(UTC)
        return self.revoked_at is None and (
            self.expires_at is None or instant < self.expires_at
        )
