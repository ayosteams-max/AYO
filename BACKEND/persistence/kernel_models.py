from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

KernelIdentifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,126}$")]
BoundedKey = Annotated[str, Field(min_length=8, max_length=128)]
Payload = dict[str, str | int | bool | None]


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_type: KernelIdentifier
    aggregate_type: KernelIdentifier
    aggregate_id: Annotated[str, Field(min_length=1, max_length=128)]
    source_module: KernelIdentifier
    schema_version: Annotated[int, Field(ge=1, le=32_767)] = 1
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: Payload = Field(default_factory=dict)
    correlation_id: UUID
    request_id: UUID
    command_id: UUID | None = None
    causation_id: UUID | None = None
    idempotency_key: BoundedKey | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Domain event timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def bound_payload(cls, value: Payload) -> Payload:
        if len(value) > 32:
            raise ValueError("Domain event payload exceeds 32 fields")
        for key, item in value.items():
            if not 1 <= len(key) <= 63 or not key.replace("_", "").isalnum():
                raise ValueError("Domain event payload key is invalid")
            if isinstance(item, str) and len(item) > 512:
                raise ValueError("Domain event payload value is too long")
        return value


class OutboxEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event: DomainEvent
    attempt_count: int
    available_at: datetime
    claimed_by: str | None = None


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: KernelIdentifier
    actor_reference: Annotated[str, Field(min_length=1, max_length=128)]
    idempotency_key: BoundedKey
    request_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    command_id: UUID
    correlation_id: UUID
    request_id: UUID
    response_reference: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


def canonical_request_hash(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()
