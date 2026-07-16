from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HandoffState(StrEnum):
    SEARCHING = "searching"
    OFFERING = "offering"
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"
    NO_DRIVER = "no_driver"


class HandoffOfferState(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class DispatchHandoff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    handoff_id: UUID = Field(default_factory=uuid4)
    ride_request_id: UUID
    rider_identity_id: UUID
    service_type: str = Field(pattern="^immediate_standard$")
    pickup_reference: UUID
    destination_reference: UUID
    service_zone_id: UUID
    service_zone_version: str
    validation_decision_id: UUID
    ride_request_version: int = Field(ge=1)
    ride_policy_version: str
    dispatch_policy_version: str
    state: HandoffState = HandoffState.SEARCHING
    version: int = Field(default=1, ge=1)
    created_at: datetime
    expires_at: datetime
    correlation_id: UUID
    causation_id: UUID
    idempotency_identity: str = Field(min_length=16, max_length=128)
    audit_reference: UUID
    assigned_driver_id: UUID | None = None

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("Handoff timestamps must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "DispatchHandoff":
        if self.expires_at <= self.created_at:
            raise ValueError("Handoff expiry must follow creation")
        return self


class EligibleDriverInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_id: UUID
    vehicle_id: UUID
    authorized_vehicle_id: UUID
    account_active: bool
    eligibility_status: str
    eligibility_expires_at: datetime
    vehicle_approved: bool
    supported_services: frozenset[str]
    availability: str
    availability_observed_at: datetime
    pickup_cost_seconds: int = Field(ge=0, le=14400)
    heading_consistent: bool = True
    pickup_accessible: bool = True
    conflicting_commitment: bool = False
    eligibility_policy_version: str

    @field_validator("eligibility_expires_at", "availability_observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Driver evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)


class HandoffOffer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    offer_id: UUID = Field(default_factory=uuid4)
    handoff_id: UUID
    driver_id: UUID
    vehicle_id: UUID
    state: HandoffOfferState = HandoffOfferState.CREATED
    version: int = Field(default=1, ge=1)
    created_at: datetime
    expires_at: datetime
    dispatch_policy_version: str
    pickup_cost_seconds: int

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Offer timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "HandoffOffer":
        if self.expires_at <= self.created_at:
            raise ValueError("Offer expiry must follow creation")
        return self


def rank_candidates(
    candidates: list[EligibleDriverInput], *, now: datetime, max_age_seconds: int
) -> list[EligibleDriverInput]:
    result = []
    for item in candidates:
        age = (now - item.availability_observed_at).total_seconds()
        if not (
            item.account_active
            and item.eligibility_status == "eligible"
            and item.eligibility_expires_at > now
            and item.vehicle_approved
            and item.vehicle_id == item.authorized_vehicle_id
            and "immediate_standard" in item.supported_services
            and item.availability == "available"
            and 0 <= age <= max_age_seconds
            and item.pickup_accessible
            and not item.conflicting_commitment
        ):
            continue
        result.append(item)
    return sorted(
        result,
        key=lambda x: (
            x.pickup_cost_seconds,
            not x.heading_consistent,
            str(x.driver_id),
        ),
    )
