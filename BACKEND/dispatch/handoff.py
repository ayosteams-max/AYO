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
    authenticated_session_active: bool = True
    earning_capability: str = "ride_driver"
    fatigue_eligible: bool = True
    temporary_restrictions_clear: bool = True
    traffic_evidence_fresh: bool = True
    pickup_confidence_bps: int = Field(default=10000, ge=0, le=10000)
    active_workload_count: int = Field(default=0, ge=0, le=20)
    reliability_bps: int = Field(default=5000, ge=0, le=10000)
    cancellation_history_bps: int = Field(default=0, ge=0, le=10000)
    opportunity_deficit_bps: int = Field(default=0, ge=0, le=10000)
    route_evidence_id: str = Field(
        default="legacy.pre_ap095", min_length=8, max_length=128
    )
    route_observed_at: datetime | None = None

    @field_validator(
        "eligibility_expires_at", "availability_observed_at", "route_observed_at"
    )
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
    route_evidence_id: str = Field(min_length=8, max_length=128)
    decision_reason_codes: tuple[str, ...] = Field(min_length=3, max_length=16)

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
            and item.authenticated_session_active
            and item.earning_capability == "ride_driver"
            and item.eligibility_status == "eligible"
            and item.eligibility_expires_at > now
            and item.vehicle_approved
            and item.vehicle_id == item.authorized_vehicle_id
            and "immediate_standard" in item.supported_services
            and item.availability == "available"
            and 0 <= age <= max_age_seconds
            and item.pickup_accessible
            and item.fatigue_eligible
            and item.temporary_restrictions_clear
            and item.traffic_evidence_fresh
            and item.pickup_confidence_bps >= 5000
            and 0
            <= (
                now - (item.route_observed_at or item.availability_observed_at)
            ).total_seconds()
            <= max_age_seconds
            and not item.conflicting_commitment
        ):
            continue
        result.append(item)

    def effective_cost(item: EligibleDriverInput) -> int:
        reliability_penalty = (10000 - item.reliability_bps) * 10 // 10000
        cancellation_penalty = item.cancellation_history_bps * 10 // 10000
        workload_penalty = min(item.active_workload_count * 5, 15)
        fairness_credit = item.opportunity_deficit_bps * 20 // 10000
        return max(
            0,
            item.pickup_cost_seconds
            + reliability_penalty
            + cancellation_penalty
            + workload_penalty
            - fairness_credit,
        )

    return sorted(
        result,
        key=lambda x: (
            effective_cost(x),
            x.pickup_cost_seconds,
            not x.heading_consistent,
            str(x.driver_id),
        ),
    )


def decision_reason_codes(item: EligibleDriverInput) -> tuple[str, ...]:
    reasons = ["pickup_eta_primary", "safety_eligible", "ride_driver_online"]
    if item.opportunity_deficit_bps:
        reasons.append("bounded_fair_opportunity")
    if item.reliability_bps != 5000:
        reasons.append("bounded_reliability_evidence")
    if item.cancellation_history_bps:
        reasons.append("bounded_cancellation_history")
    if item.active_workload_count:
        reasons.append("active_workload_considered")
    reasons.extend(("route_intelligence_evidence", "policy_versioned"))
    return tuple(reasons)
