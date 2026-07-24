from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServiceAreaState(StrEnum):
    PLANNED = "planned"
    APPROVED = "approved"
    ACTIVE = "active"
    TEMPORARILY_SUSPENDED = "temporarily_suspended"
    RETIRED = "retired"


class RideProductCode(StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"
    AIRPORT_TRANSFER = "airport_transfer"
    ACCESSIBLE_PRIVATE_RIDE = "accessible_private_ride"


class ProductAvailabilityState(StrEnum):
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    NOT_YET_LAUNCHED = "not_yet_launched"
    RETIRED = "retired"


class AvailabilityOutcome(StrEnum):
    AVAILABLE = "available"
    OUTSIDE_SERVICE_AREA = "outside_service_area"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    NOT_YET_LAUNCHED = "not_yet_launched"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    SERVICE_AREA_INACTIVE = "service_area_inactive"
    UNKNOWN_OR_UNVERIFIABLE = "unknown_or_unverifiable"


class ServiceArea(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_area_id: UUID
    internal_name: str = Field(min_length=1, max_length=128)
    customer_safe_label: str | None = Field(default=None, max_length=128)
    state: ServiceAreaState = ServiceAreaState.PLANNED
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def valid_interval(self) -> "ServiceArea":
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must follow effective_from")
        return self


class ServiceAreaGeometry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    geometry_id: UUID
    service_area_id: UUID
    geometry_version: int = Field(ge=1)
    provenance: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_at: datetime


class ProductAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    availability_id: UUID
    service_area_id: UUID
    product_code: RideProductCode
    state: ProductAvailabilityState
    effective_from: datetime
    effective_until: datetime | None = None
    reason_classification: str = Field(min_length=1, max_length=63)
    provenance: str = Field(min_length=1, max_length=256)
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class AvailabilityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_id: UUID
    ride_request_id: UUID | None = None
    ride_request_version: int | None = Field(default=None, ge=1)
    pickup_reference: str = Field(min_length=1, max_length=200)
    product_code: RideProductCode
    intended_service_at: datetime
    evaluated_at: datetime
    service_area_id: UUID | None = None
    service_area_version: int | None = None
    geometry_id: UUID | None = None
    geometry_version: int | None = None
    availability_id: UUID | None = None
    availability_version: int | None = None
    outcome: AvailabilityOutcome
    correlation_id: UUID
    request_id: UUID
    command_id: UUID | None = None
    supersedes_evaluation_id: UUID | None = None


class CustomerSafeAvailability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    can_choose_another_area: bool
    can_book_for_trusted_person: bool
