from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RideState(StrEnum):
    SEARCHING = "searching"
    OFFERING = "offering"
    ASSIGNED = "assigned"
    NO_DRIVER_AVAILABLE = "no_driver_available"
    RIDER_CANCELLED = "rider_cancelled"


class OfferState(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DriverAvailability(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ASSIGNED = "assigned"
    OFFLINE = "offline"
    SUSPENDED = "suspended"


class PlaceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    place_id: Annotated[str, Field(min_length=8, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]


class QuoteSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quote_id: UUID
    amount_minor: Annotated[int, Field(ge=0)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    pricing_version: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Quote expiry must be timezone-aware")
        return value.astimezone(UTC)


class CreateRideCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pickup: PlaceSnapshot
    destination: PlaceSnapshot
    service_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,39}$")]
    quote: QuoteSnapshot

    @model_validator(mode="after")
    def different_places(self) -> "CreateRideCommand":
        if self.pickup.place_id == self.destination.place_id:
            raise ValueError("Pickup and destination must differ")
        return self


class DispatchRide(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_id: UUID = Field(default_factory=uuid4)
    rider_id: UUID
    pickup: PlaceSnapshot
    destination: PlaceSnapshot
    service_type: str
    quote: QuoteSnapshot
    state: RideState = RideState.SEARCHING
    accepted_at: datetime
    updated_at: datetime
    version: Annotated[int, Field(ge=1)] = 1
    assigned_driver_id: UUID | None = None
    active_offer_id: UUID | None = None
    attempted_driver_ids: frozenset[UUID] = frozenset()

    @field_validator("accepted_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Ride timestamps must be timezone-aware")
        return value.astimezone(UTC)


class DriverReputation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    completed_trips: Annotated[int, Field(ge=0)] = 0
    reliable_completions: Annotated[int, Field(ge=0)] = 0
    avoidable_cancellations: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def valid_counts(self) -> "DriverReputation":
        if self.reliable_completions > self.completed_trips:
            raise ValueError("Reliable completions cannot exceed completed trips")
        return self

    def trust(self, minimum_history: int) -> tuple[Decimal, bool]:
        if self.completed_trips < minimum_history:
            return Decimal("0.5000"), True
        reliability = Decimal(self.reliable_completions) / Decimal(self.completed_trips)
        cancellation_penalty = min(
            Decimal(self.avoidable_cancellations) / Decimal(self.completed_trips),
            Decimal("0.25"),
        )
        return max(Decimal("0"), reliability - cancellation_penalty), False


class DriverCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: UUID
    availability: DriverAvailability
    verified: bool
    safety_eligible: bool
    service_types: frozenset[str]
    pickup_eta_seconds: Annotated[int, Field(ge=0, le=14_400)]
    location_observed_at: datetime
    opportunity_deficit: Annotated[Decimal, Field(ge=0, le=1)] = Decimal("0")
    reputation: DriverReputation = DriverReputation()

    @field_validator("location_observed_at")
    @classmethod
    def location_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location time must be timezone-aware")
        return value.astimezone(UTC)


class DispatchPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,62}$")]
    offer_timeout_seconds: Annotated[int, Field(ge=5, le=120)] = 15
    maximum_location_age_seconds: Annotated[int, Field(ge=5, le=300)] = 45
    minimum_reputation_history: Annotated[int, Field(ge=1, le=1_000)] = 20
    maximum_fairness_eta_tradeoff_seconds: Annotated[int, Field(ge=0, le=120)] = 20
    reliability_penalty_seconds: Annotated[int, Field(ge=0, le=120)] = 10
    maximum_candidates: Annotated[int, Field(ge=1, le=100)] = 20


class DispatchScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    driver_id: UUID
    pickup_eta_seconds: int
    effective_eta_seconds: int
    trust_score: Decimal
    neutral_reputation: bool
    fairness_credit_seconds: int
    reliability_penalty_seconds: int
    policy_version: str
    reason_codes: tuple[str, ...]


class DriverOffer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    offer_id: UUID = Field(default_factory=uuid4)
    ride_id: UUID
    driver_id: UUID
    state: OfferState = OfferState.CREATED
    created_at: datetime
    expires_at: datetime
    policy_version: str
    score: DispatchScore
    version: Annotated[int, Field(ge=1)] = 1

    @field_validator("created_at", "expires_at")
    @classmethod
    def offer_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Offer timestamps must be timezone-aware")
        return value.astimezone(UTC)


class RideProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ride_id: UUID
    state: RideState
    version: int
    accepted_at: datetime
    pickup: PlaceSnapshot
    destination: PlaceSnapshot
    service_type: str
    estimated_fare_minor: int
    currency: str
    assigned_driver_id: UUID | None


def project_ride(ride: DispatchRide) -> RideProjection:
    return RideProjection(
        ride_id=ride.ride_id,
        state=ride.state,
        version=ride.version,
        accepted_at=ride.accepted_at,
        pickup=ride.pickup,
        destination=ride.destination,
        service_type=ride.service_type,
        estimated_fare_minor=ride.quote.amount_minor,
        currency=ride.quote.currency,
        assigned_driver_id=ride.assigned_driver_id,
    )
