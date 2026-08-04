from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EarningCapability(StrEnum):
    RIDE_DRIVER = "ride_driver"
    FOOD_COURIER = "food_courier"
    PARCEL_COURIER = "parcel_courier"
    HOME_SERVICE_PROVIDER = "home_service_provider"


class WorkerSessionState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


class WorkerCapabilitySession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    worker_session_id: UUID = Field(default_factory=uuid4)
    identity_id: UUID
    identity_session_id: UUID
    capability: EarningCapability
    vehicle_id: UUID | None = None
    service_zone_id: UUID | None = None
    state: WorkerSessionState = WorkerSessionState.ONLINE
    started_at: datetime
    last_seen_at: datetime
    stopped_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @field_validator("started_at", "last_seen_at", "stopped_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Worker-session timestamps must be timezone-aware")
        return value.astimezone(UTC)


class WorkerSessionConflict(RuntimeError):
    pass
