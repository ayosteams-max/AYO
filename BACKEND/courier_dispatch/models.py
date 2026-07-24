from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourierDispatchState(StrEnum):
    WAITING = "waiting_for_courier"
    OFFERED = "courier_offered"
    ASSIGNED = "courier_assigned"
    CANCELLED = "dispatch_cancelled"
    UNFULFILLED = "dispatch_unfulfilled"


class CourierDispatchAction(StrEnum):
    OFFER = "offer"
    ACCEPT = "accept"
    DECLINE = "decline"
    EXPIRE = "expire"
    REVOKE = "revoke"
    RELEASE = "release_assignment"
    CANCEL = "cancel"
    CONCLUDE_UNFULFILLED = "conclude_unfulfilled"


class CourierOfferState(StrEnum):
    ACTIVE = "active"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CourierAssignmentState(StrEnum):
    ASSIGNED = "assigned"
    RELEASED = "released_before_pickup"
    CANCELLED = "cancelled_before_pickup"


class EligibilityEvidenceType(StrEnum):
    PARTICIPATION = "canonical_courier_participation"
    OPERATING_AUTHORITY = "active_courier_operating_authority"
    AVAILABILITY = "current_availability"
    LOCATION_FRESHNESS = "location_freshness"
    SERVICE_PRODUCT = "service_product_eligibility"
    SAFETY_FATIGUE = "fatigue_safety_eligibility"
    VEHICLE_CAPACITY = "vehicle_capacity_eligibility"


class CourierEligibilityEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_type: EligibilityEvidenceType
    source_reference: UUID
    source_version: int = Field(ge=1)
    eligible: bool
    observed_at: datetime
    valid_until: datetime

    @field_validator("observed_at", "valid_until")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("eligibility timestamp must be timezone-aware")
        return value


class CourierOffer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    offer_id: UUID
    dispatch_id: UUID
    attempt_number: int = Field(ge=1)
    courier_identity_id: UUID
    state: CourierOfferState
    offered_at: datetime
    expires_at: datetime
    resolved_at: datetime | None = None
    resolution_actor_identity_id: UUID | None = None
    resolution_reason: str | None = None
    version: int = Field(ge=1)


class CourierAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assignment_id: UUID
    dispatch_id: UUID
    offer_id: UUID
    attempt_number: int = Field(ge=1)
    courier_identity_id: UUID
    state: CourierAssignmentState
    assigned_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None
    version: int = Field(ge=1)


class CourierDispatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    dispatch_id: UUID
    order_id: UUID
    merchant_id: UUID
    readiness_message_id: UUID
    state: CourierDispatchState
    version: int
    policy_code: str
    policy_version: int
    attempt_number: int = 0
    active_offer_id: UUID | None = None
    active_assignment_id: UUID | None = None
    offered_courier_identity_id: UUID | None
    assigned_courier_identity_id: UUID | None
    created_at: datetime
    offered_at: datetime | None
    assigned_at: datetime | None
    updated_at: datetime


class CourierDispatchEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID
    dispatch_id: UUID
    order_id: UUID
    event_type: str
    from_state: CourierDispatchState | None
    to_state: CourierDispatchState
    actor_identity_id: UUID | None
    version: int
    occurred_at: datetime
    correlation_id: UUID | None = None
    causation_id: UUID | None = None


class MerchantCourierDispatchView(BaseModel):
    model_config = ConfigDict(frozen=True)
    dispatch: CourierDispatchRequest
    events: tuple[CourierDispatchEvent, ...]
    offers: tuple[CourierOffer, ...] = ()
    assignments: tuple[CourierAssignment, ...] = ()
