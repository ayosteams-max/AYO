from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,62}$")]
BasisPoints = Annotated[int, Field(ge=0, le=10_000)]


class ReservationState(StrEnum):
    REQUESTED = "requested"
    PASSENGER_CONFIRMATION_PENDING = "passenger_confirmation_pending"
    ACCEPTED = "accepted"
    PLANNING = "planning"
    DRIVER_COMMITTED = "driver_committed"
    REVALIDATING = "revalidating"
    REASSIGNING = "reassigning"
    FALLBACK_DISPATCH = "fallback_dispatch"
    DRIVER_EN_ROUTE = "driver_en_route"
    READY_FOR_PICKUP = "ready_for_pickup"
    ACTIVATED_AS_RIDE = "activated_as_ride"
    FULFILLED = "fulfilled"
    RIDER_CANCELLED = "rider_cancelled"
    PASSENGER_DECLINED = "passenger_declined"
    CONFIRMATION_EXPIRED = "confirmation_expired"
    EXPIRED = "expired"
    NO_DRIVER_AVAILABLE = "no_driver_available"
    OPERATIONAL_REVIEW = "operational_review"


TERMINAL_STATES = frozenset(
    {
        ReservationState.FULFILLED,
        ReservationState.RIDER_CANCELLED,
        ReservationState.PASSENGER_DECLINED,
        ReservationState.CONFIRMATION_EXPIRED,
        ReservationState.EXPIRED,
        ReservationState.NO_DRIVER_AVAILABLE,
    }
)


class ParticipantRole(StrEnum):
    BOOKER = "booker"
    PASSENGER = "passenger"
    FUTURE_PAYER = "future_payer"
    TRUSTED_CONTACT = "trusted_contact"


class ParticipantKind(StrEnum):
    IDENTITY = "identity"
    VERIFIED_CONTACT = "verified_contact"
    ASSISTED = "assisted"


class ConsentState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    EXPIRED = "expired"
    ASSISTED_REQUIRED = "assisted_required"


class CommitmentState(StrEnum):
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"
    CONVERTED = "converted"


class PreDispatchState(StrEnum):
    PROVISIONAL = "provisional"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"
    CONVERTED = "converted"


class FlightState(StrEnum):
    SCHEDULED = "scheduled"
    EARLY = "early"
    DELAYED = "delayed"
    LANDED = "landed"
    CANCELLED = "cancelled"
    DIVERTED = "diverted"
    UNKNOWN = "unknown"


class CheckpointType(StrEnum):
    SOFT_PLAN = "soft_plan"
    FORMAL_COMMITMENT = "formal_commitment"
    REVALIDATION = "revalidation"
    FALLBACK = "fallback"


class RecoveryAction(StrEnum):
    WAIT = "wait"
    PLAN = "plan"
    COMMIT = "commit"
    REVALIDATE = "revalidate"
    FALLBACK_DISPATCH = "fallback_dispatch"
    OPERATIONAL_REVIEW = "operational_review"


class Participant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    participant_id: UUID = Field(default_factory=uuid4)
    role: ParticipantRole
    kind: ParticipantKind
    identity_id: UUID | None = None
    contact_reference: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    consent_state: ConsentState = ConsentState.NOT_REQUIRED

    @model_validator(mode="after")
    def valid_reference(self) -> "Participant":
        if self.kind is ParticipantKind.IDENTITY and self.identity_id is None:
            raise ValueError("Identity participant requires identity_id")
        if self.kind is not ParticipantKind.IDENTITY and self.contact_reference is None:
            raise ValueError(
                "Contact or assisted participant requires contact reference"
            )
        return self


class ReservationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: UUID = Field(default_factory=uuid4)
    version: Code
    minimum_booking_lead_seconds: Annotated[int, Field(ge=300, le=604_800)] = 3_600
    maximum_booking_horizon_seconds: Annotated[int, Field(ge=3_600, le=31_536_000)] = (
        7_776_000
    )
    soft_planning_lead_seconds: Annotated[int, Field(ge=300, le=604_800)] = 86_400
    formal_commitment_lead_seconds: Annotated[int, Field(ge=300, le=604_800)] = 10_800
    revalidation_lead_seconds: Annotated[int, Field(ge=60, le=86_400)] = 3_600
    material_lateness_reduction_seconds: Annotated[int, Field(ge=1, le=3_600)] = 300
    material_reliability_gain_bps: BasisPoints = 1_000
    stability_margin_seconds: Annotated[int, Field(ge=0, le=3_600)] = 180
    maximum_soft_replacements: Annotated[int, Field(ge=0, le=20)] = 2
    maximum_formal_replacements: Annotated[int, Field(ge=0, le=20)] = 2
    fairness_eta_equivalence_seconds: Annotated[int, Field(ge=0, le=600)] = 60
    maximum_fairness_credit_bps: BasisPoints = 1_000
    minimum_prediction_confidence_bps: BasisPoints = 7_000
    maximum_current_trip_completion_seconds: Annotated[int, Field(ge=60, le=14_400)] = (
        1_800
    )
    passenger_confirmation_ttl_seconds: Annotated[int, Field(ge=60, le=604_800)] = (
        86_400
    )
    checkpoint_retry_limit: Annotated[int, Field(ge=1, le=20)] = 5

    @model_validator(mode="after")
    def valid_windows(self) -> "ReservationPolicy":
        if not (
            self.soft_planning_lead_seconds
            >= self.formal_commitment_lead_seconds
            >= self.revalidation_lead_seconds
        ):
            raise ValueError("Planning windows must be ordered")
        if self.maximum_booking_horizon_seconds <= self.minimum_booking_lead_seconds:
            raise ValueError("Booking horizon must exceed minimum lead")
        return self


class ScheduledReservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID = Field(default_factory=uuid4)
    booker_id: UUID
    passenger_participant_id: UUID
    pickup_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    destination_place_id: Annotated[str, Field(min_length=8, max_length=128)]
    service_type: Code
    quote_id: UUID
    requested_pickup_at: datetime
    requested_timezone: Annotated[str, Field(min_length=1, max_length=64)]
    state: ReservationState
    policy_id: UUID
    policy_version: Code
    created_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1
    active_soft_plan_id: UUID | None = None
    active_commitment_id: UUID | None = None
    activated_ride_id: UUID | None = None
    airport_context_id: UUID | None = None
    soft_replacement_count: Annotated[int, Field(ge=0)] = 0
    formal_replacement_count: Annotated[int, Field(ge=0)] = 0

    @field_validator("requested_pickup_at", "created_at", "updated_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Reservation timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_places(self) -> "ScheduledReservation":
        if self.pickup_place_id == self.destination_place_id:
            raise ValueError("Pickup and destination must differ")
        return self


class ScheduledCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: UUID
    eligible: bool
    safety_eligible: bool
    airport_eligible: bool = True
    pickup_eta_low_seconds: Annotated[int, Field(ge=0, le=14_400)]
    pickup_eta_high_seconds: Annotated[int, Field(ge=0, le=14_400)]
    pickup_window_success_bps: BasisPoints
    recovery_capacity_bps: BasisPoints
    opportunity_deficit_bps: BasisPoints = 0
    current_trip_completion_high_seconds: Annotated[int, Field(ge=0, le=14_400)] = 0
    prediction_confidence_bps: BasisPoints = 10_000
    location_observed_at: datetime
    has_conflicting_commitment: bool = False

    @field_validator("location_observed_at")
    @classmethod
    def aware_location(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_eta_range(self) -> "ScheduledCandidate":
        if self.pickup_eta_high_seconds < self.pickup_eta_low_seconds:
            raise ValueError("ETA range is inverted")
        return self


class CandidateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    driver_id: UUID
    policy_version: Code
    conservative_eta_seconds: int
    reliability_bps: BasisPoints
    fairness_credit_bps: BasisPoints
    effective_reliability_bps: BasisPoints
    reason_codes: tuple[Code, ...]


class SoftPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    soft_plan_id: UUID = Field(default_factory=uuid4)
    reservation_id: UUID
    driver_id: UUID
    decision: CandidateDecision
    selected_at: datetime
    expires_at: datetime
    supersedes_soft_plan_id: UUID | None = None


class DriverCommitment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commitment_id: UUID = Field(default_factory=uuid4)
    reservation_id: UUID
    driver_id: UUID
    state: CommitmentState = CommitmentState.COMMITTED
    window_started_at: datetime
    window_ended_at: datetime
    committed_at: datetime
    policy_version: Code
    reason_code: Code = "driver_committed"
    version: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def valid_window(self) -> "DriverCommitment":
        if self.window_ended_at <= self.window_started_at:
            raise ValueError("Commitment window must be positive")
        return self


class PreDispatchProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID
    driver_id: UUID
    state: PreDispatchState
    current_trip_completion_high_seconds: int
    pickup_eta_high_seconds: int
    confidence_bps: BasisPoints
    reason_codes: tuple[Code, ...]


class AirportContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    airport_context_id: UUID = Field(default_factory=uuid4)
    airport_code: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    terminal_code: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    pickup_zone_code: Code
    flight_reference: Annotated[str, Field(min_length=8, max_length=128)] | None = None
    flight_state: FlightState = FlightState.UNKNOWN
    scheduled_arrival_at: datetime | None = None
    estimated_arrival_at: datetime | None = None
    observed_at: datetime
    expires_at: datetime
    provider_version: Code

    @field_validator(
        "scheduled_arrival_at", "estimated_arrival_at", "observed_at", "expires_at"
    )
    @classmethod
    def optional_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Airport timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ReservationCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: UUID = Field(default_factory=uuid4)
    reservation_id: UUID
    kind: CheckpointType
    due_at: datetime
    attempt_count: Annotated[int, Field(ge=0)] = 0
    completed_at: datetime | None = None
    last_failure_code: Code | None = None

    @field_validator("due_at", "completed_at")
    @classmethod
    def checkpoint_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Checkpoint timestamps must be timezone-aware")
        return value.astimezone(UTC)


class RecoveryDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID
    action: RecoveryAction
    policy_version: Code
    reason_codes: tuple[Code, ...]
