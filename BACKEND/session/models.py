from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BoundedId = Annotated[str, Field(min_length=1, max_length=128)]


class SessionRecord(BaseModel):
    """Server-side session state; never contains a raw session credential."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    session_id: UUID = Field(default_factory=uuid4)
    subject_id: BoundedId
    identity_id: UUID | None = None
    device_id: UUID | None = None
    device_fingerprint_ref: (
        Annotated[bytes, Field(min_length=32, max_length=32)] | None
    ) = None
    device_category: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    application_version: Annotated[str, Field(min_length=1, max_length=32)] | None = (
        None
    )
    operating_system_family: (
        Annotated[str, Field(min_length=1, max_length=32)] | None
    ) = None
    authentication_method: Annotated[str, Field(min_length=1, max_length=32)] | None = (
        None
    )
    assurance_level: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    risk_state: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    ip_risk_ref: Annotated[bytes, Field(min_length=32, max_length=32)] | None = None
    token_family_id: UUID | None = None
    refresh_rotation_counter: Annotated[int, Field(ge=0)] = 0
    token_hash: Annotated[bytes, Field(min_length=32, max_length=32)]
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: (
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")] | None
    ) = None
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "expires_at", "last_seen_at", "revoked_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Session timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "SessionRecord":
        if self.expires_at <= self.created_at:
            raise ValueError("Session expiry must follow creation")
        if (self.revoked_at is None) != (self.revocation_reason is None):
            raise ValueError("Session revocation time and reason must be set together")
        return self

    def is_active_at(self, instant: datetime) -> bool:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Session check time must be timezone-aware")
        return self.revoked_at is None and instant.astimezone(UTC) < self.expires_at
