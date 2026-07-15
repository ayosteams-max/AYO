from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BasisPoints = Annotated[int, Field(ge=0, le=10_000)]
NonNegative = Annotated[int, Field(ge=0)]
RuleCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]


class DataQuality(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class SignalKind(StrEnum):
    AIRPORT = "airport"
    EVENT = "event"
    WEATHER = "weather"
    TRAFFIC = "traffic"


class RecommendationType(StrEnum):
    NO_CHANGE = "no_change"
    SUPPLY_GUIDANCE = "supply_guidance"
    INCENTIVE_REVIEW = "incentive_review"
    PRICE_REVIEW = "price_review"
    SUPPRESS = "suppress"
    INSUFFICIENT_DATA = "insufficient_data"


class CancellationParty(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"
    PLATFORM = "platform"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class CancellationCause(StrEnum):
    RIDER_CHANGED_PLAN = "rider_changed_plan"
    DRIVER_AVOIDABLE = "driver_avoidable"
    PICKUP_AMBIGUITY = "pickup_ambiguity"
    ETA_MISS = "eta_miss"
    COMMUNICATION_FAILURE = "communication_failure"
    EXTERNAL_DISRUPTION = "external_disruption"
    UNKNOWN = "unknown"


class MarketplaceRuleSet(BaseModel):
    """Immutable configuration. Values are proposals until leadership activates them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_set_id: UUID = Field(default_factory=uuid4)
    version: RuleCode
    effective_at: datetime
    minimum_sample_size: Annotated[int, Field(ge=1, le=100_000)] = 30
    neutral_driver_completed_trip_threshold: Annotated[int, Field(ge=1, le=1_000)] = 20
    healthy_wait_seconds: Annotated[int, Field(ge=1, le=7_200)] = 600
    healthy_idle_seconds: Annotated[int, Field(ge=1, le=86_400)] = 1_800
    healthy_no_driver_bps: BasisPoints = 500
    healthy_cancellation_bps: BasisPoints = 800
    opportunity_equivalent_eta_seconds: Annotated[int, Field(ge=0, le=120)] = 20
    opportunity_maximum_credit_bps: BasisPoints = 1_500
    demand_history_weight_bps: BasisPoints = 7_500
    demand_signal_cap_bps: Annotated[int, Field(ge=10_000, le=30_000)] = 15_000
    demand_lower_band_bps: BasisPoints = 8_000
    demand_upper_band_bps: Annotated[int, Field(ge=10_000, le=20_000)] = 12_000
    surge_supply_ratio_bps: BasisPoints = 7_500
    surge_wait_pressure_bps: Annotated[int, Field(ge=10_000, le=30_000)] = 11_000
    recommendation_ttl_seconds: Annotated[int, Field(ge=30, le=3_600)] = 300
    external_delay_minimum_confidence_bps: BasisPoints = 7_000
    emergency_surge_suppressed: bool = True
    component_weights_bps: dict[str, BasisPoints] = Field(
        default={
            "rider_reliability": 3_500,
            "driver_fairness": 2_500,
            "marketplace_efficiency": 2_500,
            "business_sustainability": 1_500,
        }
    )

    @field_validator("effective_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Rule effective time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_weights(self) -> "MarketplaceRuleSet":
        required = {
            "rider_reliability",
            "driver_fairness",
            "marketplace_efficiency",
            "business_sustainability",
        }
        if set(self.component_weights_bps) != required:
            raise ValueError("Marketplace component weights must be complete")
        if sum(self.component_weights_bps.values()) != 10_000:
            raise ValueError("Marketplace component weights must total 10000")
        if self.demand_lower_band_bps > 10_000:
            raise ValueError("Demand lower band cannot exceed baseline")
        return self


class ContextSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: UUID = Field(default_factory=uuid4)
    kind: SignalKind
    code: RuleCode
    factor_bps: Annotated[int, Field(ge=0, le=30_000)] = 10_000
    confidence_bps: BasisPoints
    observed_at: datetime
    expires_at: datetime
    emergency: bool = False

    @field_validator("observed_at", "expires_at")
    @classmethod
    def signal_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Signal timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_lifetime(self) -> "ContextSignal":
        if self.expires_at <= self.observed_at:
            raise ValueError("Signal expiry must follow observation")
        return self


class MarketplaceSnapshot(BaseModel):
    """Privacy-minimized aggregate facts for one zone/service/time window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: UUID = Field(default_factory=uuid4)
    market_code: RuleCode
    zone_code: RuleCode
    service_type: RuleCode
    window_started_at: datetime
    window_ended_at: datetime
    request_count: NonNegative
    assigned_count: NonNegative
    completed_count: NonNegative
    no_driver_count: NonNegative
    rider_cancel_count: NonNegative
    driver_cancel_count: NonNegative
    pickup_wait_p90_seconds: NonNegative
    eligible_driver_count: NonNegative
    online_driver_count: NonNegative
    driver_idle_p50_seconds: NonNegative
    driver_deadhead_p50_seconds: NonNegative
    opportunity_bottom_decile_minor: NonNegative
    opportunity_median_minor: NonNegative
    estimated_contribution_minor: int
    forecast_baseline_requests: NonNegative
    sample_size: NonNegative
    signals: tuple[ContextSignal, ...] = ()

    @field_validator("window_started_at", "window_ended_at")
    @classmethod
    def snapshot_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Snapshot timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def consistent_counts(self) -> "MarketplaceSnapshot":
        if self.window_ended_at <= self.window_started_at:
            raise ValueError("Snapshot window must be positive")
        if self.assigned_count > self.request_count:
            raise ValueError("Assignments cannot exceed requests")
        if self.completed_count > self.assigned_count:
            raise ValueError("Completions cannot exceed assignments")
        return self


class ScoreComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: RuleCode
    score_bps: BasisPoints
    reason_codes: tuple[RuleCode, ...]


class DemandForecast(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_requests: NonNegative
    lower_requests: NonNegative
    upper_requests: NonNegative
    factor_bps: Annotated[int, Field(ge=0, le=30_000)]
    context_codes: tuple[RuleCode, ...]
    quality: DataQuality


class MarketplaceRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    snapshot_id: UUID
    rule_set_id: UUID
    rule_version: RuleCode
    generated_at: datetime
    expires_at: datetime
    health_score_bps: BasisPoints
    components: tuple[ScoreComponent, ...]
    demand_forecast: DemandForecast
    recommendation: RecommendationType
    reason_codes: tuple[RuleCode, ...]
    quality: DataQuality

    @field_validator("generated_at", "expires_at")
    @classmethod
    def recommendation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Recommendation timestamps must be timezone-aware")
        return value.astimezone(UTC)


class DriverOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: UUID
    completed_trips: NonNegative
    pickup_eta_seconds: NonNegative
    eligible_online_seconds: NonNegative
    idle_seconds: NonNegative
    offered_earnings_minor: NonNegative


class OpportunityAdjustment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: UUID
    credit_bps: BasisPoints
    neutral_reputation: bool
    reason_codes: tuple[RuleCode, ...]


class CancellationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cancelled_by: CancellationParty
    rider_reason: RuleCode | None = None
    driver_reason: RuleCode | None = None
    pickup_ambiguous: bool = False
    communication_failed: bool = False
    eta_error_seconds: int = 0
    external_signal_confidence_bps: BasisPoints = 0


class CancellationAttribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    responsible_party: CancellationParty
    cause: CancellationCause
    protected_from_driver_penalty: bool
    reason_codes: tuple[RuleCode, ...]


class DelayEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_seconds: NonNegative
    actual_seconds: NonNegative
    signal_kind: SignalKind | None = None
    confidence_bps: BasisPoints = 0
    platform_route_failure: bool = False


class DelayProtection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protected: bool
    protected_seconds: NonNegative
    reason_codes: tuple[RuleCode, ...]
