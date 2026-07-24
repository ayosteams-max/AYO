from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from BACKEND.merchant_orders.models import MerchantOrderView


class PreparationAction(StrEnum):
    START = "start"
    UPDATE_PROGRESS = "update_progress"
    MARK_READY = "mark_ready"


class PreparationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order_id: UUID
    merchant_id: UUID
    started_at: datetime
    estimated_duration_seconds: int = Field(ge=60, le=14_400)
    estimated_ready_at: datetime
    progress_percent: int = Field(ge=0, le=100)
    latest_delay_reason_code: str | None = Field(default=None, max_length=63)
    latest_delay_message: str | None = Field(default=None, max_length=240)
    updated_at: datetime
    ready_at: datetime | None = None

    @field_validator("started_at", "estimated_ready_at", "updated_at", "ready_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preparation timestamp must be timezone-aware")
        return value.astimezone(UTC)


class PreparationEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    merchant_id: UUID
    event_type: str = Field(pattern=r"^commerce\.preparation\.[a-z_]{3,32}$")
    actor_identity_id: UUID
    order_version: int = Field(ge=1)
    progress_percent: int = Field(ge=0, le=100)
    estimated_duration_seconds: int | None = Field(default=None, ge=60, le=14_400)
    delay_reason_code: str | None = Field(default=None, max_length=63)
    delay_message: str | None = Field(default=None, max_length=240)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def event_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preparation event timestamp must be timezone-aware")
        return value.astimezone(UTC)


class PreparationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    order: MerchantOrderView
    preparation: PreparationRecord | None
    preparation_events: tuple[PreparationEvent, ...]
