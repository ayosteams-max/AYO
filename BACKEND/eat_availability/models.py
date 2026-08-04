from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EatAvailabilityState(StrEnum):
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    UNAVAILABLE = "unavailable"


class EatAvailabilityOutcome(StrEnum):
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    UNAVAILABLE = "unavailable"
    MERCHANT_CLOSED = "merchant_closed"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    UNKNOWN_OR_STALE = "unknown_or_stale"


class EatAvailabilityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: UUID = Field(default_factory=uuid4)
    merchant_id: UUID
    product_code: str = Field(default="ayo_eat", pattern=r"^ayo_eat$")
    area_reference: str = Field(min_length=8, max_length=200)
    coverage_reference: str = Field(min_length=8, max_length=200)
    state: EatAvailabilityState
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)
    effective_from: datetime
    effective_until: datetime | None = None
    version: int = Field(default=1, ge=1)
    created_by_identity_id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("effective_from", "effective_until", "created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("availability timestamps must be timezone-aware")
        return None if value is None else value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "EatAvailabilityPolicy":
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must follow effective_from")
        return self


class EatAvailabilityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_id: UUID = Field(default_factory=uuid4)
    policy_id: UUID | None = None
    policy_version: int | None = Field(default=None, ge=1)
    merchant_id: UUID
    area_reference: str = Field(min_length=8, max_length=200)
    coverage_reference: str = Field(min_length=8, max_length=200)
    item_references: tuple[UUID, ...] = Field(min_length=1, max_length=50)
    merchant_open: bool
    outcome: EatAvailabilityOutcome
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$", max_length=63)
    evaluated_at: datetime
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    correlation_id: UUID
    request_id: UUID

    @field_validator("evaluated_at")
    @classmethod
    def evaluation_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluation time must be timezone-aware")
        return value.astimezone(UTC)
