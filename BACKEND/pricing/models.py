from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Minor = Annotated[int, Field(ge=0, le=10_000_000_000)]
Version = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")]


class PricingPolicyStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    RETIRED = "retired"


class CalculationState(StrEnum):
    ESTIMATE_CREATED = "estimate_created"
    ESTIMATE_ACCEPTED = "estimate_accepted"
    ESTIMATE_EXPIRED = "estimate_expired"
    FINAL_INPUTS_PENDING = "final_inputs_pending"
    FINAL_CALCULATED = "final_calculated"
    REVIEW_REQUIRED = "review_required"
    FINALIZED = "finalized"
    DISPUTED = "disputed"
    CORRECTED = "corrected"
    SETTLEMENT_INSTRUCTION_READY = "settlement_instruction_ready"


class DataQuality(StrEnum):
    VERIFIED = "verified"
    APPROVED_SYNTHETIC = "approved_synthetic"
    DEGRADED = "degraded"


class PricingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: UUID = Field(default_factory=uuid4)
    policy_version: Version
    predecessor_policy_id: UUID | None = None
    service_zone_id: UUID
    service_type: str = Field(pattern=r"^immediate_standard$")
    currency: str = Field(pattern=r"^ETB$")
    base_fare_minor: Minor
    distance_rate_per_km_minor: Minor
    time_rate_per_minute_minor: Minor
    minimum_fare_minor: Minor
    commission_basis_points: int = Field(ge=0, le=10_000)
    tax_placeholder_basis_points: int = Field(default=0, ge=0, le=10_000)
    rounding_increment_minor: int = Field(ge=1, le=10_000)
    effective_from: datetime
    effective_until: datetime | None = None
    status: PricingPolicyStatus = PricingPolicyStatus.DRAFT
    made_by_identity_id: UUID
    approved_by_identity_id: UUID | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    published_by_identity_id: UUID | None = None
    created_at: datetime

    @field_validator(
        "effective_from",
        "effective_until",
        "approved_at",
        "published_at",
        "created_at",
    )
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Pricing-policy timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_policy(self) -> "PricingPolicy":
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("Policy effective window is invalid")
        if self.minimum_fare_minor < self.base_fare_minor:
            raise ValueError("Minimum fare cannot be below base fare")
        if self.approved_by_identity_id == self.made_by_identity_id:
            raise ValueError("Maker cannot approve their own policy")
        if self.status in {
            PricingPolicyStatus.APPROVED,
            PricingPolicyStatus.PUBLISHED,
        } and (self.approved_by_identity_id is None or self.approved_at is None):
            raise ValueError("Approved policy requires checker evidence")
        if self.status is PricingPolicyStatus.PUBLISHED and (
            self.published_at is None or self.published_by_identity_id is None
        ):
            raise ValueError("Published policy requires publication time")
        return self


class RouteMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    distance_meters: int = Field(ge=1, le=2_000_000)
    duration_seconds: int = Field(ge=1, le=172_800)
    observed_at: datetime
    provider_id: str = Field(min_length=2, max_length=63)
    provider_version: Version
    distance_source: str = Field(min_length=2, max_length=63)
    duration_source: str = Field(min_length=2, max_length=63)
    provenance_reference: str = Field(min_length=8, max_length=128)
    data_quality: DataQuality

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Route metrics must be timezone-aware")
        return value.astimezone(UTC)


class FareBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    currency: str = Field(pattern=r"^ETB$")
    base_minor: Minor
    distance_minor: Minor
    time_minor: Minor
    minimum_adjustment_minor: Minor
    tax_placeholder_minor: Minor
    rider_total_minor: Minor
    driver_gross_minor: Minor
    ayo_commission_minor: Minor
    driver_net_projection_minor: Minor


class FinancialTraceability(BaseModel):
    """Immutable lifecycle navigation carried by every Pricing artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_request_id: UUID
    dispatch_handoff_id: UUID | None = None
    assignment_id: UUID | None = None
    active_ride_id: UUID | None = None
    fare_estimate_id: UUID
    fare_calculation_id: UUID | None = None
    predecessor_fare_calculation_id: UUID | None = None
    ledger_transaction_id: UUID | None = None
    wallet_projection_id: UUID | None = None
    settlement_instruction_id: UUID | None = None

    @model_validator(mode="after")
    def ordered_authority_chain(self) -> "FinancialTraceability":
        if self.active_ride_id is None and self.dispatch_handoff_id is not None:
            raise ValueError("Dispatch lineage requires Active Ride")
        if self.active_ride_id is None and self.assignment_id is not None:
            raise ValueError("Assignment lineage requires Active Ride")
        if self.active_ride_id is not None and (
            self.dispatch_handoff_id is None or self.assignment_id is None
        ):
            raise ValueError("Active Ride trace requires Dispatch lineage")
        if self.fare_calculation_id is not None:
            if self.active_ride_id is None:
                raise ValueError("Fare calculation trace requires Active Ride lineage")
            if self.dispatch_handoff_id is None or self.assignment_id is None:
                raise ValueError("Fare calculation trace requires Dispatch lineage")
            if self.fare_estimate_id is None:
                raise ValueError("Fare calculation trace requires Fare Estimate lineage")
        if self.predecessor_fare_calculation_id is not None and (
            self.fare_calculation_id is None
            or self.predecessor_fare_calculation_id == self.fare_calculation_id
        ):
            raise ValueError("Correction trace requires a distinct calculation")
        if self.ledger_transaction_id is not None and self.fare_calculation_id is None:
            raise ValueError("Ledger lineage requires fare calculation lineage")
        if self.wallet_projection_id is not None and self.fare_calculation_id is None:
            raise ValueError("Wallet lineage requires fare calculation lineage")
        if self.settlement_instruction_id is not None and self.fare_calculation_id is None:
            raise ValueError("Settlement lineage requires fare calculation lineage")
        return self


class CalculationLineage(BaseModel):
    """Complete immutable evidence needed to reproduce a Pricing result."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    formula_version: Version
    policy_id: UUID
    policy_version: Version
    predecessor_policy_id: UUID | None
    made_by_identity_id: UUID
    approved_by_identity_id: UUID
    approved_at: datetime
    published_by_identity_id: UUID
    published_at: datetime
    distance_meters: int
    duration_seconds: int
    distance_source: str
    duration_source: str
    route_metric_provider_id: str
    route_metric_provider_version: Version
    route_metric_provenance_reference: str
    route_metric_observed_at: datetime
    base_fare_minor: Minor
    distance_rate_per_km_minor: Minor
    time_rate_per_minute_minor: Minor
    minimum_fare_minor: Minor
    commission_basis_points: int
    tax_placeholder_basis_points: int
    raw_distance_numerator: int
    raw_distance_denominator: int
    raw_time_numerator: int
    raw_time_denominator: int
    pre_minimum_minor: Minor
    minimum_adjustment_minor: Minor
    pre_rounding_minor: Minor
    rounding_increment_minor: int
    rounded_fare_before_tax_minor: Minor
    commission_numerator: int
    commission_denominator: int
    tax_numerator: int
    tax_denominator: int
    canonical_input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    audit_event_id: UUID
    correlation_id: UUID
    causation_id: UUID


class FareEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    estimate_id: UUID = Field(default_factory=uuid4)
    ride_request_id: UUID
    rider_identity_id: UUID
    policy_id: UUID
    policy_version: Version
    service_zone_id: UUID
    service_type: str = Field(pattern=r"^immediate_standard$")
    metrics: RouteMetrics
    breakdown: FareBreakdown
    financial_traceability: FinancialTraceability
    calculation_lineage: CalculationLineage
    state: CalculationState = CalculationState.ESTIMATE_CREATED
    expires_at: datetime
    created_at: datetime
    reason_codes: tuple[str, ...]
    translation_keys: tuple[str, ...]
    audit_reference: UUID
    correlation_id: UUID
    causation_id: UUID

    @field_validator("expires_at", "created_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Estimate timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def expiry_after_creation(self) -> "FareEstimate":
        if self.expires_at <= self.created_at:
            raise ValueError("Estimate expiry must follow creation")
        return self


class EstimateAcceptance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    acceptance_id: UUID = Field(default_factory=uuid4)
    estimate_id: UUID
    rider_identity_id: UUID
    accepted_policy_version: Version
    accepted_amount_minor: Minor
    currency: str = Field(pattern=r"^ETB$")
    accepted_at: datetime
    idempotency_key: str = Field(min_length=16, max_length=128)
    audit_reference: UUID

    @field_validator("accepted_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Acceptance timestamp must be timezone-aware")
        return value.astimezone(UTC)


class FareCalculation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    calculation_id: UUID = Field(default_factory=uuid4)
    estimate_id: UUID
    acceptance_id: UUID
    ride_id: UUID
    rider_identity_id: UUID
    driver_identity_id: UUID
    policy_id: UUID
    policy_version: Version
    state: CalculationState
    metrics: RouteMetrics
    breakdown: FareBreakdown
    financial_traceability: FinancialTraceability
    calculation_lineage: CalculationLineage
    estimate_difference_minor: int = Field(ge=-10_000_000_000, le=10_000_000_000)
    predecessor_calculation_id: UUID | None = None
    reason_codes: tuple[str, ...]
    translation_keys: tuple[str, ...]
    audit_reference: UUID
    calculated_at: datetime
    settlement_instruction_ready: bool = False

    @field_validator("calculated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Calculation timestamp must be timezone-aware")
        return value.astimezone(UTC)


class FinancialJourney(BaseModel):
    """Role-restricted, immutable ride-to-finance navigation projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    active_ride_id: UUID
    ride_request_id: UUID
    dispatch_handoff_id: UUID
    assignment_id: UUID
    fare_estimates: tuple[FareEstimate, ...]
    fare_calculations: tuple[FareCalculation, ...]
