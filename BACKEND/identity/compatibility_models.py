from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubjectKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"
    OTHER = "other"


class AccountLifecycle(StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    LOCKED = "locked"
    SUSPENDED = "suspended"
    CLOSED = "closed"


ACCOUNT_TRANSITIONS: dict[AccountLifecycle, frozenset[AccountLifecycle]] = {
    AccountLifecycle.PENDING_ACTIVATION: frozenset(
        {AccountLifecycle.ACTIVE, AccountLifecycle.CLOSED}
    ),
    AccountLifecycle.ACTIVE: frozenset(
        {
            AccountLifecycle.LOCKED,
            AccountLifecycle.SUSPENDED,
            AccountLifecycle.CLOSED,
        }
    ),
    AccountLifecycle.LOCKED: frozenset(
        {
            AccountLifecycle.ACTIVE,
            AccountLifecycle.SUSPENDED,
            AccountLifecycle.CLOSED,
        }
    ),
    AccountLifecycle.SUSPENDED: frozenset(
        {AccountLifecycle.ACTIVE, AccountLifecycle.CLOSED}
    ),
    AccountLifecycle.CLOSED: frozenset(),
}


class LegacySemantic(StrEnum):
    CANONICAL_SUBJECT = "canonical_subject"
    ACCOUNT = "account"
    BUSINESS_PARTICIPANT = "business_participant"
    AUTHENTICATION_ACTOR = "authentication_actor"
    AUTHORIZATION_PRINCIPAL = "authorization_principal"
    RESOURCE_OWNER = "resource_owner"
    AUDIT_ACTOR = "audit_actor"
    AMBIGUOUS = "ambiguous_legacy_reference"


class MappingState(StrEnum):
    SUBJECT_MAPPED = "subject_mapped"
    ACCOUNT_MAPPED = "account_mapped"
    AMBIGUOUS = "ambiguous"


class CanonicalSubject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_id: UUID = Field(default_factory=uuid4)
    subject_kind: SubjectKind
    created_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Subject timestamp must be timezone-aware")
        return value.astimezone(UTC)


class IdentityAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID = Field(default_factory=uuid4)
    subject_id: UUID
    state: AccountLifecycle = AccountLifecycle.PENDING_ACTIVATION
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1
    failed_attempt_count: Annotated[int, Field(ge=0)] = 0
    last_failed_at: datetime | None = None
    failed_window_started_at: datetime | None = None
    credential_change_required: bool = False
    credential_change_reason: str | None = None
    credential_change_provenance: str | None = None

    @field_validator(
        "created_at", "updated_at", "last_failed_at", "failed_window_started_at"
    )
    @classmethod
    def aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Account timestamp must be timezone-aware")
        return value.astimezone(UTC)

    def transition(
        self, target: AccountLifecycle, *, at: datetime
    ) -> "IdentityAccount":
        if target not in ACCOUNT_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid account transition: {self.state}->{target}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("Account transition timestamp must be timezone-aware")
        return self.model_copy(
            update={"state": target, "updated_at": at.astimezone(UTC)}
        )


class LegacyIdentityMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mapping_id: UUID = Field(default_factory=uuid4)
    legacy_identity_id: UUID
    subject_id: UUID
    account_id: UUID | None = None
    semantic: LegacySemantic
    mapping_state: MappingState
    provenance: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")]
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Mapping timestamp must be timezone-aware")
        return value.astimezone(UTC)
