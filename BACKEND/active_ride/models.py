from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]


class ActiveRideState(StrEnum):
    REQUEST_ACCEPTED = "request_accepted"
    SEARCHING = "searching"
    OFFERING = "offering"
    ASSIGNED = "assigned"
    DRIVER_EN_ROUTE = "driver_en_route"
    DRIVER_ARRIVED = "driver_arrived"
    PICKUP_VERIFICATION_PENDING = "pickup_verification_pending"
    PICKUP_VERIFIED = "pickup_verified"
    IN_PROGRESS = "in_progress"
    DESTINATION_APPROACHING = "destination_approaching"
    COMPLETION_PENDING = "completion_pending"
    COMPLETED = "completed"
    REASSIGNING = "reassigning"
    CANCELLATION_PENDING = "cancellation_pending"
    CANCELLED = "cancelled"
    NO_SHOW_REVIEW = "no_show_review"
    NO_DRIVER_AVAILABLE = "no_driver_available"
    OPERATIONAL_RECOVERY = "operational_recovery"
    OPERATIONAL_REVIEW = "operational_review"


TERMINAL_STATES = frozenset(
    {
        ActiveRideState.COMPLETED,
        ActiveRideState.CANCELLED,
        ActiveRideState.NO_DRIVER_AVAILABLE,
    }
)


class ActorRole(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"
    WORKER = "worker"
    SUPPORT = "support"


class ResponsibilityClass(StrEnum):
    RIDER = "rider_responsibility"
    DRIVER = "driver_responsibility"
    AYO = "ayo_responsibility"
    EXTERNAL = "external_disruption"
    SHARED = "shared_responsibility"
    INSUFFICIENT = "insufficient_evidence"


class CommandStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    STALE = "stale"
    OFFLINE = "offline"


class ConfidenceLevel(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


class DataQualityStatus(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    STALE = "stale"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


class PickupConfidence(StrEnum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class LocationSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: datetime
    accuracy_meters: Annotated[int, Field(ge=0, le=10_000)]
    latitude_e6: Annotated[int, Field(ge=-90_000_000, le=90_000_000)]
    longitude_e6: Annotated[int, Field(ge=-180_000_000, le=180_000_000)]

    @field_validator("observed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location observation must be timezone-aware")
        return value.astimezone(UTC)


class ActiveRide(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ride_id: UUID = Field(default_factory=uuid4)
    rider_id: UUID
    driver_id: UUID | None = None
    reservation_id: UUID | None = None
    assignment_id: UUID | None = None
    state: ActiveRideState
    pickup_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    destination_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    service_type: Code
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1
    last_sequence: Annotated[int, Field(ge=0)] = 0
    driver_changed: bool = False

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ride timestamp must be timezone-aware")
        return value.astimezone(UTC)


class RideEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    sequence: Annotated[int, Field(ge=1)]
    aggregate_version: Annotated[int, Field(ge=1)]
    event_type: Code
    schema_version: Annotated[int, Field(ge=1)] = 1
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    evidence_type: Code
    submitted_by_role: ActorRole
    observed_at: datetime
    responsibility: ResponsibilityClass = ResponsibilityClass.INSUFFICIENT
    reason_code: Code
    evidence_references: tuple[str, ...] = ()


class ConfidencePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_set_id: Code = "active_ride_confidence"
    version: Code = "v1"
    maximum_location_age_seconds: Annotated[int, Field(ge=5, le=900)] = 90
    watch_eta_increase_seconds: Annotated[int, Field(ge=30, le=3600)] = 180
    at_risk_eta_increase_seconds: Annotated[int, Field(ge=60, le=7200)] = 420
    stagnation_seconds: Annotated[int, Field(ge=30, le=7200)] = 600
    hysteresis_seconds: Annotated[int, Field(ge=0, le=1800)] = 120
    alert_cooldown_seconds: Annotated[int, Field(ge=30, le=86_400)] = 600
    decision_ttl_seconds: Annotated[int, Field(ge=10, le=3600)] = 300


class ConfidenceSignals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    driver_location_age_seconds: int | None = Field(default=None, ge=0)
    rider_location_age_seconds: int | None = Field(default=None, ge=0)
    pickup_eta_increase_seconds: int | None = Field(default=None, ge=0)
    lifecycle_stagnation_seconds: int = Field(default=0, ge=0)
    driver_moving_away: bool = False
    unexpected_stop: bool = False
    locations_conflict: bool = False
    repeated_verification_failure: bool = False
    provider_unavailable: bool = False
    verified_external_delay: bool = False
    anomaly_duration_seconds: int = Field(default=0, ge=0, le=86_400)


class ConfidenceDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    confidence_decision_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    rule_set_id: Code
    rule_set_version: Code
    health_level: ConfidenceLevel
    reason_codes: tuple[Code, ...]
    signal_freshness: dict[str, str]
    data_quality_status: DataQualityStatus
    generated_at: datetime
    expires_at: datetime
    recommended_actions: tuple[Code, ...]


class PickupRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recommendation_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    policy_id: Code = "dynamic_pickup"
    policy_version: Code = "v1"
    primary_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    fallback_place_id: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    entrance_or_gate: Annotated[str, Field(max_length=120)] | None = None
    terminal_or_zone: Annotated[str, Field(max_length=80)] | None = None
    walking_time_min_seconds: int | None = Field(default=None, ge=0, le=7200)
    walking_time_max_seconds: int | None = Field(default=None, ge=0, le=7200)
    driver_approach_guidance: Annotated[str, Field(max_length=300)]
    accessibility_supported: bool
    confidence: PickupConfidence
    source_freshness: dict[str, str]
    reason_codes: tuple[Code, ...]
    generated_at: datetime
    expires_at: datetime
    material_change: bool = False
    change_status: Annotated[
        str, Field(pattern=r"^(not_required|proposed|confirmed|declined)$")
    ] = "not_required"

    @model_validator(mode="after")
    def walking_range(self) -> "PickupRecommendation":
        if (
            self.walking_time_min_seconds is not None
            and self.walking_time_max_seconds is not None
            and self.walking_time_min_seconds > self.walking_time_max_seconds
        ):
            raise ValueError("Walking-time minimum exceeds maximum")
        if self.material_change and self.change_status == "not_required":
            raise ValueError("Material pickup change requires proposal status")
        return self
