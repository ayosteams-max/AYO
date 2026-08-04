from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,62}$", max_length=63)]


class RideRequestState(StrEnum):
    DRAFT = "draft"
    REQUESTED = "requested"
    VALIDATING = "validating"
    READY_FOR_DISPATCH = "ready_for_dispatch"
    VALIDATION_FAILED = "validation_failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RideServiceType(StrEnum):
    IMMEDIATE_STANDARD = "immediate_standard"


class PaymentIntentType(StrEnum):
    CASH_COMPATIBLE = "cash_compatible"


class LocationSource(StrEnum):
    RIDER_SELECTED = "rider_selected"
    DEVICE_OBSERVATION = "device_observation"
    STRUCTURED_ADDRESS = "structured_address"
    LANDMARK = "landmark"


class PickupSafetyStatus(StrEnum):
    UNVERIFIED = "unverified"
    RECOMMENDED = "recommended"
    RESTRICTED = "restricted"


class ValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class Coordinate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class LocationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    coordinate: Coordinate
    source: LocationSource
    observed_at: datetime
    accuracy_metres: Annotated[float, Field(gt=0, le=10000)] | None = None
    structured_address: Annotated[str, Field(max_length=512)] | None = None
    landmark_reference: Annotated[str, Field(max_length=128)] | None = None
    note: Annotated[str, Field(max_length=280)] | None = None
    map_confidence_bps: Annotated[int, Field(ge=0, le=10000)] = 0

    @field_validator("observed_at")
    @classmethod
    def observed_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location observation must be timezone-aware")
        return value.astimezone(UTC)


class PickupDefinition(LocationMetadata):
    pickup_id: UUID = Field(default_factory=uuid4)
    entrance_reference: Annotated[str, Field(max_length=128)] | None = None
    exact_stop_reference: Annotated[str, Field(max_length=128)] | None = None
    airport_terminal_reference: Annotated[str, Field(max_length=128)] | None = None
    airport_zone_reference: Annotated[str, Field(max_length=128)] | None = None
    reference_photo_metadata_reference: Annotated[str, Field(max_length=128)] | None = (
        None
    )
    safety_status: PickupSafetyStatus = PickupSafetyStatus.UNVERIFIED
    policy_version: Code


class DestinationDefinition(LocationMetadata):
    destination_id: UUID = Field(default_factory=uuid4)


class RideRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID = Field(default_factory=uuid4)
    client_request_id: UUID
    rider_identity_id: UUID
    state: RideRequestState = RideRequestState.REQUESTED
    service_type: RideServiceType = RideServiceType.IMMEDIATE_STANDARD
    payment_intent: PaymentIntentType = PaymentIntentType.CASH_COMPATIBLE
    pickup_id: UUID
    destination_id: UUID
    service_zone_id: UUID | None = None
    consent_policy_version: Code
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    cancellation_reason: Code | None = None

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ride-request timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_expiry(self) -> "RideRequest":
        if self.expires_at <= self.created_at:
            raise ValueError("Ride request expiry must follow creation")
        return self


class ServiceZone(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    zone_id: UUID = Field(default_factory=uuid4)
    code: Code
    version: Code
    min_latitude: float = Field(ge=-90, le=90)
    max_latitude: float = Field(ge=-90, le=90)
    min_longitude: float = Field(ge=-180, le=180)
    max_longitude: float = Field(ge=-180, le=180)
    prohibited_rectangles: tuple[tuple[float, float, float, float], ...] = ()
    supported_service_types: frozenset[RideServiceType]
    active_from: datetime
    active_until: datetime | None = None
    policy_version: Code

    @field_validator("active_from", "active_until")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Service-zone timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_bounds(self) -> "ServiceZone":
        if (
            self.min_latitude >= self.max_latitude
            or self.min_longitude >= self.max_longitude
        ):
            raise ValueError("Service-zone bounds must have positive area")
        if self.active_until is not None and self.active_until <= self.active_from:
            raise ValueError("Service-zone active-until must follow active-from")
        return self


class ValidationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Code
    maximum_accuracy_metres: Annotated[float, Field(gt=0, le=10000)]
    maximum_observation_age_seconds: Annotated[int, Field(ge=1, le=86400)]
    minimum_separation_metres: Annotated[float, Field(gt=0, le=100000)]
    request_ttl_seconds: Annotated[int, Field(ge=30, le=86400)]
    prohibit_multiple_active_requests: bool = True
    effective_from: datetime
    effective_until: datetime | None = None

    @field_validator("effective_from", "effective_until")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Validation-policy timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_period(self) -> "ValidationPolicy":
        if (
            self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError(
                "Validation policy effective-until must follow effective-from"
            )
        return self


class ValidationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    policy_version: Code
    zone_id: UUID | None
    zone_version: Code | None
    status: ValidationStatus
    reason_codes: tuple[Code, ...]
    invalid_fields: tuple[Code, ...]
    evidence_freshness_seconds: int | None
    audit_reference: UUID = Field(default_factory=uuid4)
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Validation timestamp must be timezone-aware")
        return value.astimezone(UTC)


class MobilityRideRequestState(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class ScheduleIntentType(StrEnum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"


class LuggagePreference(StrEnum):
    NONE = "none"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class RideIntentPreferences(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accessibility_needs: tuple[Code, ...] = Field(default=(), max_length=16)
    luggage: LuggagePreference = LuggagePreference.NONE
    quiet_ride: bool = False
    child_seat: bool = False
    child_seat_count: Annotated[int, Field(ge=0, le=4)] = 0

    @model_validator(mode="after")
    def consistent_child_seat(self) -> "RideIntentPreferences":
        if self.child_seat != (self.child_seat_count > 0):
            raise ValueError(
                "Child-seat preference and child-seat count must be consistent"
            )
        if len(set(self.accessibility_needs)) != len(self.accessibility_needs):
            raise ValueError("Accessibility needs must be unique")
        return self


LocationReference = Annotated[
    str,
    Field(
        min_length=3,
        max_length=200,
        pattern=r"^[a-z][a-z0-9_.-]{1,62}:[A-Za-z0-9][A-Za-z0-9_.:/-]{0,135}$",
    ),
]


class PassengerMobilityRideRequest(BaseModel):
    """Canonical R1 travel intent; fulfillment belongs to other domains."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    model_version: Annotated[int, Field(ge=2, le=2)] = 2
    client_request_id: UUID
    requester_subject_id: UUID
    passenger_subject_id: UUID
    state: MobilityRideRequestState = MobilityRideRequestState.DRAFT
    pickup_reference: LocationReference
    destination_reference: LocationReference
    stop_references: tuple[LocationReference, ...] = Field(default=(), max_length=8)
    schedule_intent: ScheduleIntentType
    scheduled_for: datetime | None = None
    passenger_count: Annotated[int, Field(ge=1, le=8)]
    preferences: RideIntentPreferences = Field(default_factory=RideIntentPreferences)
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @field_validator("created_at", "updated_at", "expires_at", "scheduled_for")
    @classmethod
    def mobility_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ride Request timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_intent(self) -> "PassengerMobilityRideRequest":
        if self.expires_at <= self.created_at:
            raise ValueError("Ride Request expiry must follow creation")
        if self.pickup_reference == self.destination_reference:
            raise ValueError("Pickup and destination must differ")
        locations = (
            self.pickup_reference,
            self.destination_reference,
            *self.stop_references,
        )
        if len(set(locations)) != len(locations):
            raise ValueError("Ride Request locations must be distinct")
        if (
            self.schedule_intent is ScheduleIntentType.IMMEDIATE
            and self.scheduled_for is not None
        ):
            raise ValueError("Immediate Ride Request cannot have a scheduled time")
        if (
            self.schedule_intent is ScheduleIntentType.SCHEDULED
            and self.scheduled_for is None
        ):
            raise ValueError("Scheduled Ride Request requires a scheduled time")
        return self
