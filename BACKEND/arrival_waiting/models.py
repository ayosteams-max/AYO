from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]
BasisPoints = Annotated[int, Field(ge=0, le=10_000)]


class ArrivalState(StrEnum):
    ARRIVAL_UNVERIFIED = "arrival_unverified"
    ARRIVAL_VERIFIED = "arrival_verified"
    WAIT_PAUSED = "wait_paused"
    WAIT_INVALIDATED = "wait_invalidated"


class ReadinessClass(StrEnum):
    READY = "ready"
    MOVING_TO_PICKUP = "moving_to_pickup"
    LIKELY_ON_TIME = "likely_on_time"
    MAY_BE_LATE = "may_be_late"
    UNLIKELY_ON_TIME = "unlikely_on_time"
    INSUFFICIENT_DATA = "insufficient_data"


class WaitingState(StrEnum):
    FREE_WAIT_ACTIVE = "free_wait_active"
    FREE_WAIT_ENDING = "free_wait_ending"
    WAIT_PAUSED = "wait_paused"
    WAIT_INVALIDATED = "wait_invalidated"
    EVIDENCE_READY = "evidence_ready"


class ResponsibilityClass(StrEnum):
    RIDER = "rider_responsibility"
    DRIVER = "driver_responsibility"
    AYO = "ayo_responsibility"
    EXTERNAL = "external_disruption"
    SHARED = "shared_responsibility"
    INSUFFICIENT = "insufficient_evidence"


class RideOrigin(StrEnum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"


class PickupContext(StrEnum):
    AIRPORT = "airport"
    HOTEL = "hotel"
    HOSPITAL = "hospital"
    SHOPPING_CENTRE = "shopping_centre"
    RESIDENTIAL = "residential"
    UNIVERSITY = "university"
    STADIUM = "stadium"
    MARKET = "market"


class PickupPointKind(StrEnum):
    MAIN_GATE = "main_gate"
    EMERGENCY_ENTRANCE = "emergency_entrance"
    TERMINAL = "terminal"
    TAXI_BAY = "taxi_bay"
    SIDE_ENTRANCE = "side_entrance"
    NAMED_PICKUP_POINT = "named_pickup_point"


class ServiceContext(StrEnum):
    STANDARD = "standard"
    AIRPORT_STANDARD = "airport_standard"
    AIRPORT_PREMIUM = "airport_premium"


class DepartureBehavior(StrEnum):
    PAUSE = "pause"
    INVALIDATE = "invalidate"


class LocationObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: datetime
    sequence: Annotated[int, Field(ge=0)]
    latitude_e6: Annotated[int, Field(ge=-90_000_000, le=90_000_000)]
    longitude_e6: Annotated[int, Field(ge=-180_000_000, le=180_000_000)]
    accuracy_meters: Annotated[int, Field(ge=0, le=10_000)]
    speed_cm_per_second: Annotated[int, Field(ge=0, le=20_000)]
    heading_degrees: Annotated[int, Field(ge=0, le=359)] | None = None

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location time must be timezone-aware")
        return value.astimezone(UTC)


class ArrivalSignals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observation: LocationObservation
    approved_pickup_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    pickup_recommendation_id: UUID
    pickup_recommendation_version: Code
    pickup_zone_id: Annotated[str, Field(min_length=3, max_length=128)]
    inside_pickup_zone: bool
    pickup_confidence_bps: BasisPoints
    map_confidence_bps: BasisPoints
    seconds_stationary: Annotated[int, Field(ge=0, le=86_400)]
    approach_consistent: bool
    heading_reliable: bool
    accessible_pickup: bool
    operationally_available: bool
    unsafe_or_restricted: bool = False
    service_context: ServiceContext = ServiceContext.STANDARD
    airport_terminal_code: Annotated[str, Field(max_length=32)] | None = None
    airport_zone_match: bool = True
    airport_context_fresh: bool = True
    airport_staging_constraint_satisfied: bool = True
    airport_access_permitted: bool = True
    airport_congestion: bool = False
    airport_zone_closed: bool = False
    flight_delay_context: bool = False


class ArrivalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: Code
    version: Code
    maximum_location_age_seconds: Annotated[int, Field(ge=1, le=900)]
    maximum_accuracy_meters: Annotated[int, Field(ge=1, le=500)]
    maximum_stationary_speed_cm_per_second: Annotated[int, Field(ge=0, le=2_000)]
    minimum_stationary_seconds: Annotated[int, Field(ge=1, le=3_600)]
    minimum_pickup_confidence_bps: BasisPoints
    minimum_map_confidence_bps: BasisPoints
    minimum_verification_confidence_bps: BasisPoints


class ArrivalEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evaluation_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    assignment_id: UUID
    state: ArrivalState
    confidence_bps: BasisPoints
    reason_codes: tuple[Code, ...]
    explanation_code: Code
    pickup_place_id: str
    pickup_zone_id: str
    pickup_recommendation_id: UUID
    pickup_recommendation_version: Code
    observation_sequence: int
    evaluated_at: datetime


class ReadinessSignals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rider_location_age_seconds: int | None = Field(default=None, ge=0, le=86_400)
    rider_location_accuracy_meters: int | None = Field(default=None, ge=0, le=10_000)
    moving_toward_pickup: bool | None = None
    within_pickup_zone: bool = False
    rider_walking_eta_seconds: int | None = Field(default=None, ge=0, le=14_400)
    driver_eta_seconds: int | None = Field(default=None, ge=0, le=14_400)
    venue_context_possible: bool = False
    pickup_confidence_bps: BasisPoints
    connectivity_degraded: bool = False


class ReadinessPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: Code
    version: Code
    maximum_location_age_seconds: Annotated[int, Field(ge=1, le=900)]
    maximum_accuracy_meters: Annotated[int, Field(ge=1, le=1_000)]
    minimum_confidence_bps: BasisPoints
    notification_confidence_bps: BasisPoints
    notification_cooldown_seconds: Annotated[int, Field(ge=1, le=86_400)]
    maximum_notifications_per_ride: Annotated[int, Field(ge=0, le=20)]
    lateness_margin_seconds: Annotated[int, Field(ge=0, le=3_600)]


class ReadinessDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    classification: ReadinessClass
    confidence_bps: BasisPoints
    reason_codes: tuple[Code, ...]
    explanation_code: Code
    policy_id: Code
    policy_version: Code
    evaluated_at: datetime
    expires_at: datetime
    notification_recommended: bool
    notification_reason_code: Code


class WaitingPolicyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: UUID = Field(default_factory=uuid4)
    version: Code
    city_code: Code
    ride_origin: RideOrigin | None = None
    pickup_context: PickupContext | None = None
    service_context: ServiceContext | None = None
    assisted: bool | None = None
    accessibility_accommodation: bool | None = None
    severe_weather: bool | None = None
    operational_override_code: Code | None = None
    effective_from: datetime
    effective_until: datetime | None = None
    priority: Annotated[int, Field(ge=0, le=10_000)] = 0
    free_wait_seconds: Annotated[int, Field(ge=1, le=86_400)]
    ending_warning_seconds: Annotated[int, Field(ge=0, le=86_400)]
    departure_behavior: DepartureBehavior
    pause_on_insufficient_quality: bool
    maximum_location_age_seconds: Annotated[int, Field(ge=1, le=900)]
    minimum_location_confidence_bps: BasisPoints
    reasonable_notification_required: bool = True

    @field_validator("effective_from", "effective_until")
    @classmethod
    def aware_policy_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Policy time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_window(self) -> "WaitingPolicyDefinition":
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("Policy effective window must be positive")
        if self.ending_warning_seconds >= self.free_wait_seconds:
            raise ValueError("Ending warning must be shorter than free wait")
        return self


class WaitingPolicyContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    city_code: Code
    ride_origin: RideOrigin
    pickup_context: PickupContext
    service_context: ServiceContext
    assisted: bool = False
    accessibility_accommodation: bool = False
    severe_weather: bool = False
    operational_override_code: Code | None = None


class WaitingPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    snapshot_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    source_policy_id: UUID
    source_policy_version: Code
    context: WaitingPolicyContext
    matched_dimensions: tuple[Code, ...]
    selected_at: datetime
    free_wait_seconds: int
    ending_warning_seconds: int
    departure_behavior: DepartureBehavior
    pause_on_insufficient_quality: bool
    maximum_location_age_seconds: int
    minimum_location_confidence_bps: int
    reasonable_notification_required: bool


class WaitingSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    session_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    assignment_id: UUID
    arrival_evaluation_id: UUID
    policy_snapshot_id: UUID
    state: WaitingState
    version: Annotated[int, Field(ge=1)] = 1
    verified_arrival_at: datetime
    started_at: datetime
    free_wait_deadline: datetime
    updated_at: datetime
    total_paused_seconds: Annotated[int, Field(ge=0)] = 0
    paused_at: datetime | None = None
    last_observation_sequence: Annotated[int, Field(ge=0)]
    reason_codes: tuple[Code, ...]


class ContinuitySignals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    inside_pickup_zone: bool
    location_age_seconds: Annotated[int, Field(ge=0, le=86_400)]
    location_confidence_bps: BasisPoints
    driver_available: bool
    pickup_guidance_valid: bool
    reasonable_notification: bool
    platform_failure: bool = False
    map_or_eta_failure: bool = False
    external_disruption: bool = False
    unsafe_or_inaccessible: bool = False
    airport_zone_confusion: bool = False
    road_closure: bool = False
    emergency: bool = False
    weak_network_uncertainty: bool = False
    driver_materially_late: bool = False


class EvidenceDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    session_id: UUID
    ready: bool
    responsibility: ResponsibilityClass
    confidence_bps: BasisPoints
    reason_codes: tuple[Code, ...]
    suppression_reason_codes: tuple[Code, ...]
    explanation_code: Code
    evaluated_at: datetime


class ExactStoppingPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    latitude_e6: Annotated[int, Field(ge=-90_000_000, le=90_000_000)]
    longitude_e6: Annotated[int, Field(ge=-180_000_000, le=180_000_000)]
    heading_degrees: Annotated[int, Field(ge=0, le=359)] | None = None
    curb_side_code: Code | None = None
    position_confidence_bps: BasisPoints


class PickupReferencePhotoReference(BaseModel):
    """Future verified metadata reference; contains no image, URL or storage detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reference_id: UUID
    version: Code
    verification_code: Code
    provenance_code: Code
    alt_text_en: Annotated[str, Field(min_length=1, max_length=240)]
    alt_text_am: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    verified_at: datetime
    expires_at: datetime


class NamedPickupPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_point_id: UUID
    kind: PickupPointKind
    name_en: Annotated[str, Field(min_length=1, max_length=160)]
    name_am: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    exact_stopping_position: ExactStoppingPosition
    walking_instruction_en: Annotated[str, Field(min_length=1, max_length=500)]
    walking_instruction_am: (
        Annotated[str, Field(min_length=1, max_length=500)] | None
    ) = None
    accessibility_code: Code | None = None
    reference_photo: PickupReferencePhotoReference | None = None


class WalkingGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_point_id: UUID
    origin_observation_sequence: Annotated[int, Field(ge=0)]
    destination: ExactStoppingPosition
    distance_meters: Annotated[int, Field(ge=0, le=100_000)]
    duration_seconds: Annotated[int, Field(ge=0, le=86_400)]
    instruction_en: Annotated[str, Field(min_length=1, max_length=1000)]
    instruction_am: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    confidence_bps: BasisPoints
    route_version: Code
    generated_at: datetime
    expires_at: datetime


class WalkingGuidanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pickup_point_id: UUID
    rider_position: LocationObservation


class LandmarkReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    landmark_id: UUID
    canonical_name_en: Annotated[str, Field(min_length=1, max_length=160)]
    canonical_name_am: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    aliases_en: tuple[Annotated[str, Field(min_length=1, max_length=160)], ...] = ()
    aliases_am: tuple[Annotated[str, Field(min_length=1, max_length=160)], ...] = ()
    entrance_or_gate: Annotated[str, Field(max_length=160)] | None = None
    terminal_code: Annotated[str, Field(max_length=32)] | None = None
    side_of_road_guidance: Annotated[str, Field(max_length=240)] | None = None
    provenance_code: Code
    confidence_bps: BasisPoints
    observed_at: datetime
    expires_at: datetime
    ambiguous: bool = False
    user_submission_unverified: bool = False
    named_pickup_points: tuple[NamedPickupPoint, ...] = ()


class AirportContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    airport_code: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    terminal_code: Annotated[str, Field(min_length=1, max_length=32)]
    pickup_zone_id: Annotated[str, Field(min_length=3, max_length=128)]
    service_context: ServiceContext
    staging_required: bool
    access_permitted: bool
    flight_delay_context: bool = False
    congestion: bool = False
    zone_closed: bool = False
    observed_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def airport_service(self) -> "AirportContext":
        if self.service_context not in {
            ServiceContext.AIRPORT_STANDARD,
            ServiceContext.AIRPORT_PREMIUM,
        }:
            raise ValueError("Airport context requires an airport service")
        return self
