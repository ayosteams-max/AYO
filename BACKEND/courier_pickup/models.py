from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CourierPickupState(StrEnum):
    ASSIGNED = "courier_assigned"
    TRAVELLING = "travelling_to_merchant"
    ARRIVED = "arrived_at_merchant"
    WAITING = "waiting_for_pickup"
    ENDED_BEFORE_CUSTODY = "pickup_attempt_ended_before_custody"


class CourierPickupAction(StrEnum):
    START_TRAVEL = "start_travel"
    MARK_ARRIVED = "mark_arrived"
    ACKNOWLEDGE_ARRIVAL = "acknowledge_arrival"
    CORRECT_ARRIVAL = "correct_arrival"
    CORRECT_WAITING = "correct_waiting"
    END_ATTEMPT = "end_attempt_before_custody"


class CourierPickupExceptionReason(StrEnum):
    ASSIGNMENT_CLOSED = "assignment_closed_or_revoked"
    MERCHANT_LOCATION_UNREACHABLE = "merchant_location_unreachable"
    MERCHANT_NOT_FOUND = "merchant_not_found"
    MERCHANT_UNAVAILABLE = "merchant_unavailable"
    ORDER_NOT_READY = "order_not_ready"
    READINESS_CORRECTED = "readiness_corrected"
    COURIER_UNABLE = "courier_unable_to_continue"
    AUTHORITY_FAILURE = "authority_or_identity_failure"
    DUPLICATE_OR_INVALID = "duplicate_or_invalid_attempt"
    OTHER_REVIEW = "other_review_required"


class CourierPickupEvidenceKind(StrEnum):
    ASSIGNMENT_ADMITTED = "assignment_admitted"
    TRAVEL_STARTED = "travel_started"
    ARRIVAL_DECLARED = "arrival_declared"
    MERCHANT_ACKNOWLEDGED = "merchant_acknowledged"
    WAITING_OBSERVED = "waiting_observed"
    LOCATION_CORROBORATED = "location_corroborated"
    ATTEMPT_ENDED = "attempt_ended_before_custody"
    ARRIVAL_CORRECTED = "arrival_corrected"
    WAITING_CORRECTED = "waiting_corrected"


class CourierPickupRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    pickup_id: UUID
    dispatch_id: UUID
    assignment_id: UUID | None = None
    assignment_version: int = Field(ge=1)
    attempt_number: int = Field(ge=1)
    order_id: UUID
    merchant_id: UUID
    assigned_courier_identity_id: UUID
    assignment_message_id: UUID
    policy_code: str = "AYO_COURIER_PICKUP_POLICY_V1"
    policy_version: int = Field(default=1, ge=1)
    state: CourierPickupState
    version: int
    assigned_at: datetime
    travelling_at: datetime | None
    arrived_at: datetime | None
    merchant_acknowledged_at: datetime | None
    waiting_duration_seconds: int | None
    terminal_reason: CourierPickupExceptionReason | None = None
    custody_accepted_at: datetime | None = None
    updated_at: datetime


class CourierPickupEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID
    pickup_id: UUID
    order_id: UUID
    event_type: str
    from_state: CourierPickupState | None
    to_state: CourierPickupState
    actor_identity_id: UUID | None
    version: int
    occurred_at: datetime
    correlation_id: UUID | None = None
    causation_id: UUID | None = None


class CourierPickupEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID
    pickup_id: UUID
    pickup_version: int = Field(ge=1)
    kind: CourierPickupEvidenceKind
    actor_identity_id: UUID | None = None
    acting_for_identity_id: UUID | None = None
    merchant_id: UUID | None = None
    authority_basis: str | None = None
    source_reference: UUID | None = None
    source_version: int | None = Field(default=None, ge=1)
    reason: CourierPickupExceptionReason | None = None
    waiting_duration_seconds: int | None = Field(default=None, ge=0)
    occurred_at: datetime
    correlation_id: UUID
    causation_id: UUID


class CourierPickupView(BaseModel):
    model_config = ConfigDict(frozen=True)
    pickup: CourierPickupRecord
    events: tuple[CourierPickupEvent, ...]
    evidence: tuple[CourierPickupEvidence, ...] = ()
