from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PerformanceMetric(StrEnum):
    VERIFIED_ONBOARDING = "verified_onboarding"
    APPROVAL_QUALITY = "approval_quality"
    CORRECTION_RATE = "correction_rate"
    REJECTION_RATE = "rejection_rate"
    OWNER_SATISFACTION = "owner_satisfaction"
    COMPLETION_QUALITY = "completion_quality"
    DOCUMENTATION_QUALITY = "documentation_quality"
    TIMELINESS = "timeliness"
    TERRITORY_ACTIVITY = "territory_activity"
    DUPLICATE_ONBOARDING_RISK = "duplicate_onboarding_risk"
    FRAUD_RISK = "fraud_risk"
    MISCONDUCT_RISK = "misconduct_risk"
    MISLEADING_MERCHANT_RISK = "misleading_merchant_risk"
    PRESSURE_SELLING_RISK = "pressure_selling_risk"
    UNRESOLVED_QUALITY_RISK = "unresolved_quality_risk"


class EvidenceUnit(StrEnum):
    COUNT = "count"
    BASIS_POINTS = "basis_points"
    SECONDS = "seconds"
    BOOLEAN = "boolean"


class ReadinessRequirement(StrEnum):
    TRAINING_COMPLETE = "training_complete"
    CODE_OF_CONDUCT_CURRENT = "code_of_conduct_current"
    VERIFICATION_CURRENT = "verification_current"
    ASSIGNMENT_READY = "assignment_ready"
    QUALITY_STANDING = "quality_standing"


class RecommendationKind(StrEnum):
    OUTSTANDING_PERFORMANCE = "outstanding_performance"
    CONSISTENT_QUALITY = "consistent_quality"
    EXCELLENT_CUSTOMER_TREATMENT = "excellent_customer_treatment"
    EXCEPTIONAL_MERCHANT_SUPPORT = "exceptional_merchant_support"
    PROMOTION_CANDIDATE = "promotion_candidate"
    LEADERSHIP_CANDIDATE = "leadership_candidate"
    ADDITIONAL_TRAINING = "additional_training"
    MENTORING = "mentoring"
    QUALITY_REVIEW = "quality_review"


class PerformanceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    territory_id: UUID | None = None
    metric: PerformanceMetric
    value: int = Field(ge=0)
    unit: EvidenceUnit
    source_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    source_event_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    window_starts_at: datetime
    window_ends_at: datetime
    policy_version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,62}$")
    recorded_by_identity_id: UUID
    supersedes_evidence_id: UUID | None = None
    recorded_at: datetime

    @field_validator("window_starts_at", "window_ends_at", "recorded_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("performance timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def window(self) -> "PerformanceEvidence":
        if self.window_ends_at <= self.window_starts_at:
            raise ValueError("performance evidence window invalid")
        if self.unit is EvidenceUnit.BASIS_POINTS and self.value > 10_000:
            raise ValueError("basis points out of range")
        if self.unit is EvidenceUnit.BOOLEAN and self.value not in (0, 1):
            raise ValueError("boolean evidence must be zero or one")
        return self


class ReadinessAssertion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assertion_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    requirement: ReadinessRequirement
    satisfied: bool
    source_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    source_event_id: UUID
    evidence_reference: str = Field(min_length=16, max_length=160)
    effective_at: datetime
    expires_at: datetime | None = None
    recorded_by_identity_id: UUID
    recorded_at: datetime

    @field_validator("effective_at", "expires_at", "recorded_at")
    @classmethod
    def utc_optional(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("readiness timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validity_window(self) -> "ReadinessAssertion":
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("readiness validity window invalid")
        return self


class ReadinessView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    partner_id: UUID
    ready: bool
    satisfied: tuple[ReadinessRequirement, ...]
    missing: tuple[ReadinessRequirement, ...]
    expired: tuple[ReadinessRequirement, ...]


class PerformanceRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recommendation_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    kind: RecommendationKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    confidence_bps: int = Field(ge=0, le=10_000)
    reasoning: str = Field(min_length=20, max_length=2000)
    risks: tuple[str, ...] = Field(min_length=1, max_length=20)
    intelligence_domain: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$")
    policy_version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,62}$")
    recommended_by_identity_id: UUID
    created_at: datetime
    status: str = "recommendation_only"

    @field_validator("created_at")
    @classmethod
    def utc_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recommendation timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("status")
    @classmethod
    def recommendation_only(cls, value: str) -> str:
        if value != "recommendation_only":
            raise ValueError("performance recommendations cannot execute decisions")
        return value


class RepresentativePerformanceView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    readiness: ReadinessView
    evidence: tuple[PerformanceEvidence, ...]
    recommendations: tuple[PerformanceRecommendation, ...]


class TerritoryPerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    territory_id: UUID | None
    representative_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    workload_count: int = Field(ge=0)
    approval_rate_bps: int = Field(ge=0, le=10_000)
    correction_rate_bps: int = Field(ge=0, le=10_000)
    rejection_rate_bps: int = Field(ge=0, le=10_000)
    recommendation_candidates: int = Field(ge=0)
