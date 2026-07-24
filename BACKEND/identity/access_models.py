from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PasswordCredential(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    credential_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    credential_version: Annotated[int, Field(ge=1)]
    scheme: Annotated[str, Field(min_length=3, max_length=32)]
    verifier: Annotated[str, Field(min_length=32, max_length=512, repr=False)]
    created_at: datetime
    superseded_at: datetime | None = None

    @field_validator("created_at", "superseded_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Credential timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)


class AccountSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    client_reference: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    created_at: datetime
    last_used_at: datetime
    absolute_expires_at: datetime
    inactivity_seconds: Annotated[int, Field(ge=60, le=2_592_000)]
    revoked_at: datetime | None = None
    revocation_reason: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")] | None
    ) = None
    rotated_from_session_id: UUID | None = None
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "last_used_at", "absolute_expires_at", "revoked_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Session timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)

    def active_at(self, at: datetime) -> bool:
        instant = at.astimezone(UTC)
        inactive_at = self.last_used_at + timedelta(seconds=self.inactivity_seconds)
        return self.revoked_at is None and instant < min(
            self.absolute_expires_at, inactive_at
        )


class AccountRoleAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assignment_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    role_id: UUID
    assigned_by_account_id: UUID
    assigned_at: datetime
    revoked_at: datetime | None = None
    revoked_by_account_id: UUID | None = None
    revocation_reason: str | None = None
    version: Annotated[int, Field(ge=1)] = 1


class OwnershipRelationship(StrEnum):
    OWNER = "owner"
    DELEGATE = "delegate"
    NONE = "none"


class OwnershipResolver(Protocol):
    def relationship(
        self, *, account_id: UUID, resource_type: str, resource_id: str
    ) -> OwnershipRelationship: ...


class OwnershipDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    allowed: bool
    reason: str


class AuthenticationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authenticated: bool
    session_id: UUID | None = None
    reason: str = "authentication_failed"


class RecoveryTokenRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    purpose: str = "password_recovery"
    token_version: Annotated[int, Field(ge=1)]
    token_hash: bytes = Field(repr=False)
    state: str = "active"
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    superseded_at: datetime | None = None
    version: Annotated[int, Field(ge=1)] = 1


class RecoveryInitiationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    accepted: bool = True
    token: str | None = Field(default=None, repr=False)
    token_id: UUID | None = None
    expires_at: datetime | None = None
