from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileLifecycle(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


PROFILE_TRANSITIONS = {
    ProfileLifecycle.ACTIVE: frozenset(
        {ProfileLifecycle.SUSPENDED, ProfileLifecycle.CLOSED}
    ),
    ProfileLifecycle.SUSPENDED: frozenset(
        {ProfileLifecycle.ACTIVE, ProfileLifecycle.CLOSED}
    ),
    ProfileLifecycle.CLOSED: frozenset(),
}


class RelationshipType(StrEnum):
    FAMILY_MEMBER = "family_member"
    TRUSTED_FRIEND = "trusted_friend"
    CAREGIVER = "caregiver"
    OTHER = "other"


class RelationshipState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


RELATIONSHIP_TRANSITIONS = {
    RelationshipState.PENDING: frozenset(
        {RelationshipState.ACTIVE, RelationshipState.REMOVED}
    ),
    RelationshipState.ACTIVE: frozenset(
        {RelationshipState.SUSPENDED, RelationshipState.REMOVED}
    ),
    RelationshipState.SUSPENDED: frozenset(
        {RelationshipState.ACTIVE, RelationshipState.REMOVED}
    ),
    RelationshipState.REMOVED: frozenset(),
}


class CustomerProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profile_id: UUID = Field(default_factory=uuid4)
    subject_id: UUID
    state: ProfileLifecycle = ProfileLifecycle.ACTIVE
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    preferred_name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    language: Annotated[
        str, Field(pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$", max_length=35)
    ]
    region: Annotated[str, Field(pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,8})?$", max_length=63)]
    timezone: Annotated[str, Field(min_length=1, max_length=63)]
    service_area_preference: (
        Annotated[str, Field(min_length=1, max_length=80)] | None
    ) = None
    profile_image_reference: (
        Annotated[str, Field(min_length=1, max_length=200)] | None
    ) = None
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(UTC)


class HouseholdRelationship(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relationship_id: UUID = Field(default_factory=uuid4)
    inviting_subject_id: UUID
    invited_subject_id: UUID
    relationship_type: RelationshipType
    state: RelationshipState = RelationshipState.PENDING
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(UTC)


class EmergencyContact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contact_id: UUID = Field(default_factory=uuid4)
    subject_id: UUID
    contact_subject_id: UUID | None = None
    display_name: Annotated[str, Field(min_length=1, max_length=120)]
    channel_reference: Annotated[str, Field(min_length=1, max_length=200)]
    priority: Annotated[int, Field(ge=1, le=20)]
    active: bool = True
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(UTC)
