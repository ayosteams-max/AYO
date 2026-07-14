from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from BACKEND.audit.privacy import SafeAuditMetadata, validate_safe_metadata


class ActorType(StrEnum):
    ANONYMOUS = "anonymous"
    RIDER = "rider"
    DRIVER = "driver"
    STAFF = "staff"
    ADMINISTRATOR = "administrator"
    SYSTEM = "system"
    SERVICE = "service"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"
    CANCELLED = "cancelled"


BoundedIdentifier = Annotated[str, Field(min_length=1, max_length=128)]


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuditEvent(BaseModel):
    """Storage-neutral, immutable audit event contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=utc_now)
    recorded_at: datetime = Field(default_factory=utc_now)
    actor_type: ActorType
    actor_id: BoundedIdentifier | None = None
    session_id: UUID | None = None
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")]
    resource_type: BoundedIdentifier
    resource_id: BoundedIdentifier | None = None
    outcome: AuditOutcome
    reason: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")] | None = None
    correlation_id: UUID
    causation_id: UUID | None = None
    request_id: UUID | None = None
    source_module: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]
    schema_version: Annotated[int, Field(ge=1, le=32_767)] = 1
    safe_metadata: SafeAuditMetadata = Field(default_factory=dict)
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)] | None = None

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Audit timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("safe_metadata", mode="before")
    @classmethod
    def enforce_safe_metadata(cls, value: object) -> SafeAuditMetadata:
        return validate_safe_metadata(value)
