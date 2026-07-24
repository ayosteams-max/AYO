from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from BACKEND.pricing.models import FareBreakdown, RouteMetrics
from BACKEND.ride_request.models import (
    DestinationDefinition,
    PickupDefinition,
    PickupSafetyStatus,
)


class TollEvidenceState(StrEnum):
    AVAILABLE = "available"
    NONE_EVIDENCED = "none_evidenced"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class TrafficEvidenceState(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class PlaceKind(StrEnum):
    ADDRESS = "address"
    LANDMARK = "landmark"
    VERIFIED_PICKUP_ZONE = "verified_pickup_zone"
    VERIFIED_DROPOFF_ZONE = "verified_dropoff_zone"
    AIRPORT = "airport"
    HOSPITAL = "hospital"
    SHOPPING_CENTRE = "shopping_centre"
    UNIVERSITY = "university"
    HOTEL = "hotel"
    OFFICE = "office"
    TRANSPORT_HUB = "transport_hub"


class PlaceCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    place_reference: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=160)
    secondary_text: str | None = Field(default=None, max_length=160)
    kind: PlaceKind
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    verified_for_pickup: bool = False
    verified_for_dropoff: bool = False
    attribution: str = Field(min_length=1, max_length=160)


class ProviderRouteEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metrics: RouteMetrics
    geometry: tuple[tuple[float, float], ...] = Field(min_length=2, max_length=512)
    origin_accuracy_metres: float = Field(gt=0, le=10000)
    destination_accuracy_metres: float = Field(gt=0, le=10000)
    map_confidence_bps: int = Field(ge=0, le=10000)
    pickup_safety_status: PickupSafetyStatus = PickupSafetyStatus.UNVERIFIED
    traffic_state: TrafficEvidenceState
    toll_state: TollEvidenceState
    toll_amount_minor: int | None = Field(default=None, ge=0, le=10_000_000_000)
    restriction_codes: tuple[str, ...] = Field(default=(), max_length=32)
    attribution: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def toll_consistency(self) -> "ProviderRouteEvidence":
        if self.toll_state is TollEvidenceState.AVAILABLE:
            if self.toll_amount_minor is None:
                raise ValueError("Available toll evidence requires an amount")
        elif self.toll_amount_minor is not None:
            raise ValueError("Toll amount is forbidden without available evidence")
        return self


class BookingQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    quote_id: UUID = Field(default_factory=uuid4)
    policy_id: UUID
    policy_version: str
    breakdown: FareBreakdown
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Quote expiry must be timezone-aware")
        return value.astimezone(UTC)


class RoutePreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: UUID = Field(default_factory=uuid4)
    booking_session_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rider_identity_id: UUID | None = None
    pickup: PickupDefinition
    destination: DestinationDefinition
    service_zone_id: UUID
    service_zone_version: str
    service_type: str = Field(pattern=r"^immediate_standard$")
    route: ProviderRouteEvidence
    quote: BookingQuote
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    expires_at: datetime

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_expiry(self) -> "RoutePreview":
        if (
            self.expires_at <= self.created_at
            or self.quote.expires_at > self.expires_at
        ):
            raise ValueError("Evidence expiry is invalid")
        return self


class BookingConfirmation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    confirmation_id: UUID = Field(default_factory=uuid4)
    evidence_id: UUID
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_id: UUID
    ride_request_id: UUID
    rider_identity_id: UUID
    idempotency_key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Confirmation time must be timezone-aware")
        return value.astimezone(UTC)


class BookingConflict(RuntimeError):
    pass


BookingSession = Annotated[
    str, Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
]
